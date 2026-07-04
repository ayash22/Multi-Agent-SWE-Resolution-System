"""
QLoRA fine-tuning of Llama-3-8B-Instruct on the SFT-formatted code-fix
trajectory dataset produced by data/finetune/prepare_finetune_data.py.

Config (matches the spec exactly):
  - 4-bit NF4 quantization via bitsandbytes
  - LoRA: r=16, alpha=32, target_modules=[q_proj, v_proj, k_proj, o_proj]
  - TRL's SFTTrainer, 3 epochs, batch_size=4, gradient_accumulation_steps=4
  - max_seq_length=4096

Hardware notes: fits comfortably on a single 40GB A100 (Colab Pro /
Paperspace) in roughly 2-4 hours for a 500-2000 example dataset at these
settings. No GPU is available in this repository's default dev/CI
environment -- this script is meant to be run on your own GPU machine or a
cloud notebook. If you don't have GPU access, skip this step and set
LLAMA_BACKEND/LLAMA_MODEL_NAME (see agents/nodes/llama_coder_agent.py) to
use the base `llama3:8b-instruct` model via Ollama; the llama_coder_agent
node already falls back to this automatically and labels its output
accordingly so results stay honest about which weights produced a patch.

Usage:
    python train_qlora.py \
        --dataset data/finetune/sft_dataset.jsonl \
        --base-model meta-llama/Meta-Llama-3-8B-Instruct \
        --output-dir finetuning/checkpoints/swe-llama3-qlora \
        --epochs 3
"""
import argparse


def main(args):
    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise SystemExit(
            "No CUDA GPU detected. QLoRA fine-tuning requires a GPU (bitsandbytes "
            "4-bit quantization is CUDA-only). Run this script on a GPU machine "
            "(Colab Pro, Paperspace, a cloud A100/A10 instance, etc.), or skip "
            "fine-tuning and use the base Llama-3 model as documented in the README."
        )

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )

    dataset = load_dataset("json", data_files=args.dataset, split="train")
    if args.eval_split > 0:
        split_ds = dataset.train_test_split(test_size=args.eval_split, seed=42)
        train_ds, eval_ds = split_ds["train"], split_ds["test"]
    else:
        train_ds, eval_ds = dataset, None

    sft_config = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_ds is not None else "no",
        bf16=True,
        max_seq_length=4096,
        dataset_text_field="text",
        packing=False,
        report_to=["mlflow"] if args.use_mlflow else [],
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        peft_config=lora_config,
        tokenizer=tokenizer,
    )

    if args.use_mlflow:
        import mlflow
        mlflow.set_experiment("swe-llama3-qlora-finetune")
        with mlflow.start_run():
            mlflow.log_params({
                "base_model": args.base_model, "epochs": args.epochs,
                "lora_r": 16, "lora_alpha": 32, "quant": "nf4-4bit",
            })
            trainer.train()
    else:
        trainer.train()

    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"Saved LoRA adapter + tokenizer to {args.output_dir}")
    print("Next step: python finetuning/merge_weights.py "
          f"--base-model {args.base_model} --adapter-dir {args.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/finetune/sft_dataset.jsonl")
    parser.add_argument("--base-model", default="meta-llama/Meta-Llama-3-8B-Instruct")
    parser.add_argument("--output-dir", default="finetuning/checkpoints/swe-llama3-qlora")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--eval-split", type=float, default=0.05)
    parser.add_argument("--use-mlflow", action="store_true")
    main(parser.parse_args())

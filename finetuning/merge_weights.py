"""
Merges the trained LoRA adapter into the base Llama-3-8B-Instruct weights,
producing a standalone model directory that can be:
  (a) loaded directly by vLLM for production serving, or
  (b) converted to GGUF and imported into Ollama for local/dev serving.

Usage:
    python merge_weights.py \
        --base-model meta-llama/Meta-Llama-3-8B-Instruct \
        --adapter-dir finetuning/checkpoints/swe-llama3-qlora \
        --output-dir finetuning/merged/swe-llama3-merged
"""
import argparse
import os


def merge(base_model: str, adapter_dir: str, output_dir: str) -> None:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"Loading base model {base_model} in fp16 for merging...")
    base = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=torch.float16, device_map="cpu",
    )
    print(f"Loading LoRA adapter from {adapter_dir}...")
    merged = PeftModel.from_pretrained(base, adapter_dir)
    merged = merged.merge_and_unload()

    os.makedirs(output_dir, exist_ok=True)
    merged.save_pretrained(output_dir, safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    tokenizer.save_pretrained(output_dir)

    print(f"Merged model saved to {output_dir}")


def write_ollama_modelfile(merged_gguf_path: str, out_path: str) -> None:
    """Writes an Ollama Modelfile pointing at a GGUF conversion of the merged
    weights. GGUF conversion itself is done via llama.cpp's
    `convert_hf_to_gguf.py` + `llama-quantize`, which is outside this
    script's scope (it's a separate C++ toolchain) -- see the printed
    instructions below."""
    modelfile = f"""FROM {merged_gguf_path}
TEMPLATE \"\"\"{{{{ if .System }}}}<|start_header_id|>system<|end_header_id|>

{{{{ .System }}}}<|eot_id|>{{{{ end }}}}{{{{ if .Prompt }}}}<|start_header_id|>user<|end_header_id|>

{{{{ .Prompt }}}}<|eot_id|>{{{{ end }}}}<|start_header_id|>assistant<|end_header_id|>

{{{{ .Response }}}}<|eot_id|>\"\"\"
PARAMETER stop "<|eot_id|>"
PARAMETER temperature 0.2
PARAMETER num_ctx 4096
"""
    with open(out_path, "w") as f:
        f.write(modelfile)
    print(f"Wrote Ollama Modelfile to {out_path}")
    print(
        "To finish deployment:\n"
        "  1. Convert the merged HF weights to GGUF with llama.cpp:\n"
        "       python convert_hf_to_gguf.py <merged_dir> --outfile model.gguf\n"
        "       ./llama-quantize model.gguf model-q4_K_M.gguf Q4_K_M\n"
        "  2. Update the Modelfile's FROM line to point at model-q4_K_M.gguf\n"
        "  3. ollama create swe-llama3-qlora -f " + out_path
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="meta-llama/Meta-Llama-3-8B-Instruct")
    parser.add_argument("--adapter-dir", default="finetuning/checkpoints/swe-llama3-qlora")
    parser.add_argument("--output-dir", default="finetuning/merged/swe-llama3-merged")
    parser.add_argument("--write-ollama-modelfile", action="store_true")
    args = parser.parse_args()

    merge(args.base_model, args.adapter_dir, args.output_dir)
    if args.write_ollama_modelfile:
        write_ollama_modelfile(
            merged_gguf_path=os.path.join(args.output_dir, "model-q4_K_M.gguf"),
            out_path=os.path.join(args.output_dir, "Modelfile"),
        )

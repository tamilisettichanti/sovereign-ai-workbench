"""Image understanding with the local vision model."""
import base64
import io

from PIL import Image

from .. import llm, registry
from .files import resolve_input
from .ocr import extract_labels


def encode_image(path, max_side=1024):
    """Downscale before sending: smaller images are much faster on CPU."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def vision_messages(path, question, ocr_text="", labels=None):
    """`labels` is the result of ocr.extract_labels(): tag/name pairs and all tags found."""
    prompt = question.strip() or "Describe this image in detail."
    labels = labels or {}
    if labels.get("pairs"):
        prompt += ("\n\nFacts read from the image by OCR. Treat these tag-to-equipment pairs as correct "
                   "and use them exactly:\n" + "\n".join(f"- {tag}: {name}" for tag, name in labels["pairs"]))
    others = [t for t in labels.get("tags", []) if t not in {p[0] for p in labels.get("pairs", [])}]
    if others:
        prompt += "\n\nOther tags on the image (valves or instruments): " + ", ".join(others)
    if ocr_text:
        prompt += f"\n\nOther text found in the image by OCR (may contain small errors):\n{ocr_text[:800]}"
    return [
        {"role": "system", "content": "You are an engineer's assistant that reads industrial drawings, "
                                      "diagrams, photographs and scanned pages. Be specific and factual. "
                                      "List equipment tags and labels exactly as they appear."},
        {"role": "user", "content": prompt, "images": [encode_image(path)]},
    ]


def describe_image(args, ctx):
    path = resolve_input(args.get("path", ""))
    model = registry.pick("vision")
    if model is None:
        return {"ok": False, "output": "No vision model is installed and enabled."}
    try:
        labels = extract_labels(path)
    except Exception:
        labels = None
    msg = llm.chat(model["name"], vision_messages(path, args.get("question", ""), labels=labels),
                   user=ctx.get("user", "system"), purpose="vision tool")
    return {"ok": True, "output": f"[{path.name} | described by {model['label']}]\n{msg['content']}",
            "model": model["name"]}

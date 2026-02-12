import json
import uuid
import time
import requests
from pathlib import Path


COMFY_URL = "http://127.0.0.1:8188"
WORKFLOW_PATH = Path("workflows/workflows1.json")  # ตำแหน่งไฟล์ workflow2.json


def load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_workflow(model_name, positive, negative, width, height, seed, n_images):
    workflow = load_workflow()

    # Node 1 — CheckpointLoaderSimple
    workflow["1"]["inputs"]["ckpt_name"] = model_name

    # Node 2 — Positive Prompt
    workflow["2"]["inputs"]["text"] = positive

    # Node 3 — Negative Prompt
    workflow["3"]["inputs"]["text"] = negative

    # Node 4 — KSampler
    if seed is None:
        seed = int(time.time())
    workflow["4"]["inputs"]["seed"] = seed

    # Node 5 — EmptyLatentImage
    workflow["5"]["inputs"]["width"] = width
    workflow["5"]["inputs"]["height"] = height
    workflow["5"]["inputs"]["batch_size"] = n_images

    return workflow, seed


def send_workflow(workflow):
    prompt_id = str(uuid.uuid4())

    payload = {
        "prompt": workflow,
        "client_id": prompt_id
    }

    requests.post(f"{COMFY_URL}/prompt", json=payload)

    return prompt_id


def wait_for_result(prompt_id):
    """
    รอจนกว่ารูปจะถูกสร้าง แล้วดึง URL กลับมา
    """
    while True:
        time.sleep(1)

        history = requests.get(f"{COMFY_URL}/history/{prompt_id}").json()

        if prompt_id not in history:
            continue

        outputs = history[prompt_id]["outputs"]

        image_urls = []

        # SaveImage node ID = 7 ตาม workflow2.json
        for image in outputs["7"]["images"]:
            filename = image["filename"]
            subfolder = image.get("subfolder", "")
            file_url = f"{COMFY_URL}/view?filename={filename}&subfolder={subfolder}&type=output"
            image_urls.append(file_url)

        return image_urls


def generate_image_with_workflow(model_name, positive, negative, width, height, seed, n_images):
    workflow, seed_used = prepare_workflow(
        model_name=model_name,
        positive=positive,
        negative=negative,
        width=width,
        height=height,
        seed=seed,
        n_images=n_images
    )

    prompt_id = send_workflow(workflow)
    image_urls = wait_for_result(prompt_id)

    return {
        "seed": seed_used,
        "image_urls": image_urls
    }

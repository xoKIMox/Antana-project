import json
import os
import random
import re
import subprocess
import time
import uuid

import requests
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timesince import timesince
from django.views.decorators.http import require_POST

from .decorators import admin_required
from .forms import CommentForm, PostForm
from .models import (
    Comment,
    GenerateCount,
    GenerateDimension,
    GenerateHistory,
    GenerateModel,
    GenerateSetting,
    GenerateSize,
    Post,
    Profile,
    SidebarMenu,
    Tag,
)


COMFY_HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
WORKFLOW_PATH = os.path.join(os.path.dirname(__file__), "workflows", "workflows1.json")

# ==========================================
# 1. ผู้ใช้งานทั่วไป
# ==========================================

def welcome_page(request):
    return render(request, 'login_register.html')

@login_required(login_url= 'login')
def home_view(request):
    return render(request, 'home.html',{'user':request.user})

def register_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        if password != password2:
            messages.error(request, "รหัสผ่านไม่ตรงกัน")
            return redirect('register')

        # Password Validation
        if len(password) < 8:
            messages.error(request, "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร")
            return redirect('register')
        
        if not any(char.isdigit() for char in password) or not any(char.isalpha() for char in password):
             messages.error(request, "รหัสผ่านต้องประกอบด้วยตัวอักษรและตัวเลข")
             return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username ซ้ำ")
            return redirect('register')

        user = User.objects.create_user(username=username, email=email)
        user.set_password(password)
        user.save()
        messages.success(request, "สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ")
        return redirect('login')

    return render(request, 'register.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"ยินดีต้อนรับ {user.username}!")
            return redirect('post_feed')
        else:
            messages.error(request, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            return redirect('login')

    return render(request, 'login.html')
        
def logout_view(request):
    logout(request)
    messages.success(request,'คุณได้ออกจากระบบแล้ว')
    return redirect('login_register')

# ==========================================
# 2. สมาชิก
# ==========================================
# 2.1 ฟังก์ชันจัดการบัญชี

@login_required(login_url= 'login')
def profile_view(request):
    posts = Post.objects.filter(user=request.user).select_related('history', 'user__profile').prefetch_related('tags')
    return render(request, 'profile.html', {'posts': posts})


@login_required(login_url='login')
def edit_profile_view(request):
    if request.method == 'POST':
        
        user = request.user
        user.username = request.POST['username']
        user.email = request.POST['email']
        user.save()
        
        if 'profile_image' in request.FILES:
            if not hasattr(user, 'profile'):
                Profile.objects.create(user=user)
                
            user.profile.profile_image = request.FILES['profile_image']
            user.profile.save()
        
        messages.success(request, 'อัปเดทข้อมลูแล้ว')
        return redirect('profile')
    
    return render(request, 'edit_profile.html', {'user': request.user})


@login_required(login_url='login')
def change_password_view(request):
    if request.method == 'POST':
        old_password = request.POST['old_password']
        new_password = request.POST['new_password']
        confirm_password = request.POST['confirm_password']

        if old_password == new_password:
            messages.error(request, 'รหัสผ่านเดิมไม่ถูกต้อง')
            return redirect('change_password')

        if not request.user.check_password(old_password):
            messages.error(request, 'รหัสผ่านเดิมไม่ถูกต้อง')
            return redirect('change_password')

        user = request.user

        if not user.check_password(old_password):
            messages.error(request, 'รหัสผ่านเดิมไม่ถูกต้อง')
            return redirect('change_password')

        if new_password != confirm_password:
            messages.error(request, 'รหัสผ่านใหม่ไม่ตรงกัน')
            return redirect('change_password')

        user.set_password(new_password)
        user.save()

        update_session_auth_hash(request, user)

        messages.success(request, 'เปลี่ยนรหัสผ่านเรียบร้อยแล้ว')
        return redirect('profile')

    return render(request, 'change_password.html')

@login_required
def settings_view(request):
    return render(request, "settings.html")

@login_required
def delete_account_confirm(request):
    if request.method == "POST":
        user = request.user
        user.delete()
        messages.success(request, "บัญชีถูกลบเรียบร้อยแล้ว")
        return redirect("login_register")
    return render(request, "confirm_delete.html")

# ==========================================
# 2.2 ฟังก์ชันสร้างภาพ (Generate Image)
# ==========================================

@login_required(login_url='login')
def generate_view(request):
    # ============ POST: Generate Image ============
    if request.method == "POST":

        # อ่านค่าจากฟอร์ม
        model_id     = request.POST.get("model_label")
        dimension_id = request.POST.get("dimension")
        batch_raw    = request.POST.get("batch", "1")
        positive     = request.POST.get("positive_prompt", "").strip()
        negative     = request.POST.get("negative_prompt", "").strip()
        seed_str     = request.POST.get("seed", "").strip()

        # ---------------- Validate ----------------
        # batch
        try:
            batch = int(batch_raw)
        except ValueError:
            batch = 1

        # seed
        seed = None
        if seed_str:
            try:
                seed = int(seed_str)
            except ValueError:
                seed = None

        # model
        if not model_id:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบค่า model"},
                status=400
            )

        # dimension
        if not dimension_id:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบ dimension"},
                status=400
            )

        # prompt
        if not positive:
            return JsonResponse(
                {"status": "error", "message": "กรุณากรอก Prompt"},
                status=400
            )

        # ---------------- Check & Translate Prompt ----------------
        # ถ้ามี text, ให้แปลเป็น Eng เสมอ (ตาม requirement: กด generate แล้วแปลก่อนส่ง)
        if positive:
            print(f"[Generate] Translating Positive Prompt: {positive}")
            positive = translate_prompt_to_english(positive)
            print(f"[Generate] Translated Positive: {positive}")

        if negative:
            # negative ก็ควรแปลด้วยถ้าลูกค้ากรอกไทยมา
            print(f"[Generate] Translating Negative Prompt: {negative}")
            negative = translate_prompt_to_english(negative)
            print(f"[Generate] Translated Negative: {negative}")


        # ---------------- Load Model ----------------
        try:
            model_obj = GenerateModel.objects.get(id=model_id)
        except GenerateModel.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "ไม่พบโมเดลที่เลือก"
            }, status=400)

        ckpt = model_obj.value   # ชื่อไฟล์ .safetensors

        # ---------------- Load Dimension ----------------
        try:
            dim_obj = GenerateDimension.objects.get(id=dimension_id)
            raw = dim_obj.value.replace("px", "").replace(" ", "")
            width_str, height_str = raw.split("x")
            width = int(width_str)
            height = int(height_str)
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": f"Dimension ผิดรูปแบบ: {e}"
            }, status=400)

        # ---------------- Generate via ComfyUI ----------------
        try:
            result = generate_image_with_workflow(
                model_name = ckpt,
                positive   = positive,
                negative   = negative,
                seed       = seed,     # ใช้ seed จากฟอร์ม (None = auto random)
                width      = width,
                height     = height,
                n_images   = batch
            )
        except TimeoutError as e:
            return JsonResponse({
                "status": "timeout",
                "message": str(e),
            }, status=504)
        except Exception as e:
            print("Generate ERROR:", e)
            return JsonResponse({
                "status": "error",
                "message": f"ERROR Generate: {e}"
            }, status=500)

        # ดึงผลลัพธ์
        img_urls  = result.get("image_urls", [])
        seed_used = result.get("seed", seed)

        # ---------------- Save History ----------------
        # ---------------- Save History ----------------
        history_ids = []
        for url in img_urls:
            h = GenerateHistory.objects.create(
                user             = request.user,
                model_name       = model_obj.name,
                positive_prompt  = positive,
                negative_prompt  = negative,
                seed             = seed_used,
                image_url        = url, # Temporary keep original URL
                created_at       = timezone.now(),
            )
            
            # --- Download and Save to Local Storage ---
            try:
                # 1. Download content
                # url is like http://127.0.0.1:8188/view?filename=...
                # We need to ensure we can reach it.
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    # 2. Generate filename
                    unique_name = f"gen_{request.user.id}_{uuid.uuid4().hex[:8]}.png"
                    
                    # 3. Save to ImageField
                    h.image_file.save(unique_name, ContentFile(resp.content), save=True)
                    
                    # 4. Update image_url to be the local MEDIA URL
                    # This ensures frontend template usage of {{ item.image_url }} works with the local file
                    h.image_url = h.image_file.url
                    h.save()
                    
                    # Update local list so the immediate JSON response is correct
                    img_urls[img_urls.index(url)] = h.image_file.url
                    
            except Exception as e:
                print(f"Error downloading/saving image: {e}")
            # ------------------------------------------

            history_ids.append(h.id)

        # ---------------- Return JSON ----------------
        return JsonResponse({
            "status": "success",
            "images": img_urls,
            "history_ids": history_ids,
            "seed": seed_used,
            "prompt": positive,
            "negative": negative,
            "model": model_obj.name,
        })

    # ============ GET: Render Page ============
    models_available = GenerateModel.objects.filter(is_active=True)
    dimensions       = GenerateDimension.objects.filter(is_active=True)
    numbers          = GenerateCount.objects.filter(is_active=True)
    histories        = GenerateHistory.objects.filter(
        user=request.user
    ).order_by("-created_at")[:30]

    return render(
        request,
        "generate.html",
        {
            "models_available": models_available,
            "dimensions": dimensions,
            "numbers": numbers,
            "histories": histories,
        }
    )

def _as_int(x, default):
    try:
        return int(x)
    except Exception:
        return int(default)

def _mul8(x, default=512):
    """บังคับให้เป็นจำนวนที่หาร 8 ลงตัว (latent ส่วนใหญ่ต้องเป็น multiple of 8)"""
    v = _as_int(x, default)
    return max(64, (v // 8) * 8)

def _normalize_model_name(model_name: str) -> str:
    """
    แปลงชื่อที่มาจาก UI ให้เป็นไฟล์ ckpt/safetensors ที่ ComfyUI เห็นจริง
    ปรับ mapping ให้ตรงกับ checkpoints ที่คุณมีใน ComfyUI
    """
    mapping = {
        "Nova XL v9.0": "novaOrangeXL_v90.safetensors",
        "ilustmix v8.0": "ilustmix_v80.safetensors",
    }
    if not model_name:
        return "novaOrangeXL_v90.safetensors"
    if model_name.endswith(".safetensors") or model_name.endswith(".ckpt"):
        return model_name
    return mapping.get(model_name, model_name)

def _post_json(url: str, payload: dict, timeout: int = 60):
    """POST แบบ JSON พร้อม error message ที่อ่านง่าย"""
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"POST {url} failed: {e}")
    if r.status_code != 200:
        raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text}")
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"POST {url} returned non-JSON: {r.text[:500]}")

def _get_json(url: str, timeout: int = 30):
    """GET แล้วแปลงเป็น JSON พร้อมข้อความ error อ่านง่าย"""
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"GET {url} failed: {e}")
    if r.status_code != 200:
        raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text}")
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"GET {url} returned non-JSON: {r.text[:500]}")

def _poll_history(prompt_id: str, max_secs: int = 300, sleep_secs: float = 1.0):
    """
    โพลผลลัพธ์จาก /history/<prompt_id> จนกว่าจะมี outputs
    คืน dict history ของ ComfyUI
    """
    start = time.time()
    url = f"{COMFY_HOST}/history/{prompt_id}"
    while time.time() - start <= max_secs:
        data = _get_json(url, timeout=15)
        if prompt_id in data and data[prompt_id].get("outputs"):
            return data
        time.sleep(sleep_secs)
    raise TimeoutError(f"ComfyUI did not produce output within {max_secs}s for prompt_id={prompt_id}")

def _parse_label_value_csv(csv_text, as_int=False):
    """
    'A|100, B|200, C' -> [{'label':'A','value':100}, {'label':'B','value':200}, {'label':'C','value':'C'}]
    """
    out = []
    if not csv_text:
        return out
    for raw in csv_text.split(","):
        item = raw.strip()
        if not item:
            continue
        if "|" in item:
            label, val = [x.strip() for x in item.split("|", 1)]
            if as_int:
                try: val = int(val)
                except: pass
            out.append({"label": label, "value": val})
        else:
            val = int(item) if as_int and item.isdigit() else item
            out.append({"label": item, "value": val})
    return out

def _parse_map(csv_text, as_int=False, sep=":"):
    """
    'Small:512,Medium:768' -> {'Small':512, 'Medium':768}
    """
    out = {}
    if not csv_text:
        return out
    for raw in csv_text.split(","):
        item = raw.strip()
        if not item:
            continue
        if sep in item:
            k, v = [x.strip() for x in item.split(sep, 1)]
            if as_int:
                try: v = int(v)
                except: pass
            out[k] = v
    return out

def _parse_defaults(txt):
    """
    'model=x;dim=2:3;size=Small;count=1' -> {'model': 'x', 'dim':'2:3','size':'Small','count':'1'}
    """
    out = {}
    if not txt:
        return out
    for raw in txt.split(";"):
        if "=" in raw:
            k, v = [x.strip() for x in raw.split("=", 1)]
            if k:
                out[k] = v
    return out

def _get_generate_presets():
    defaults_builtin = {
        "models_available": [{"label":"Nova XL v9.0","value":"novaOrangeXL_v90.safetensors"}],
        "dimensions": [{"label":"2:3","value":"2:3"},{"label":"1:1","value":"1:1"},{"label":"16:9","value":"16:9"},{"label":"Custom","value":"Custom"}],
        "sizes": [{"label":"Small","value":512},{"label":"Medium","value":768},{"label":"Large","value":1024}],
        "numbers": [{"label":"1","value":1},{"label":"2","value":2},{"label":"3","value":3},{"label":"4","value":4}],
        "defaults": {"model":"novaOrangeXL_v90.safetensors","dim":"2:3","size":"Small","count":"1"},
        "size_px_map": {"Small":512,"Medium":768,"Large":1024},
    }

    try:
        setting = GenerateSetting.objects.first()
    except Exception:
        return defaults_builtin

    if not setting:
        return defaults_builtin

    models_av = _parse_label_value_csv(setting.models_available, as_int=False) or defaults_builtin["models_available"]
    dims      = _parse_label_value_csv(setting.dimensions,      as_int=False) or defaults_builtin["dimensions"]
    sizes     = _parse_label_value_csv(setting.sizes,           as_int=True)  or defaults_builtin["sizes"]
    numbers   = _parse_label_value_csv(setting.number_of_images,as_int=True)  or defaults_builtin["numbers"]

    dflts     = _parse_defaults(setting.defaults) or defaults_builtin["defaults"]
    size_map  = _parse_map(setting.size_px, as_int=True) or {s["label"]: s["value"] for s in sizes}

    return {
        "models_available": models_av,
        "dimensions": dims,
        "sizes": sizes,
        "numbers": numbers,
        "defaults": dflts,
        "size_px_map": size_map,
    }

# =========================
# == COMFY PAYLOAD BUILDER
# =========================
def build_prompt_graph(model_name, positive, negative, seed, width, height, n_images=1):
    """
    โหลด workflows2.json แล้วตั้งค่า node id ตามไฟล์ workflow ของคุณ:
      1: CheckpointLoaderSimple -> ckpt_name
      2: CLIPTextEncode (positive) -> text
      3: CLIPTextEncode (negative) -> text
      4: KSampler -> seed
      5: EmptyLatentImage -> width/height/batch_size
      7: SaveImage (output)
    คืน payload พร้อมส่ง /prompt
    """
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        wf = json.load(f)

    ckpt  = _normalize_model_name(model_name)
    seed  = _as_int(seed if seed not in [None, ""] else random.randint(1, 4294967295), random.randint(1, 4294967295))
    width = _mul8(width, 512)
    height = _mul8(height, 512)
    batch = max(1, _as_int(n_images or 1, 1))

    # id=1
    if "1" in wf and "inputs" in wf["1"]:
        wf["1"]["inputs"]["ckpt_name"] = ckpt
    # id=2
    if "2" in wf and "inputs" in wf["2"]:
        wf["2"]["inputs"]["text"] = positive or ""
    # id=3
    if "3" in wf and "inputs" in wf["3"]:
        wf["3"]["inputs"]["text"] = negative or ""
    # id=4
    if "4" in wf and "inputs" in wf["4"]:
        wf["4"]["inputs"]["seed"] = seed
    # id=5
    if "5" in wf and "inputs" in wf["5"]:
        wf["5"]["inputs"]["width"] = width
        wf["5"]["inputs"]["height"] = height
        wf["5"]["inputs"]["batch_size"] = max(1, int(n_images or 1))  # ถ้าอยากได้หลายรูป

    return {"prompt": wf, "client_id": "django-ui"}

def generate_image_with_workflow(model_name, positive, negative, seed, width, height, n_images=None):
    """
    ส่ง workflow ไป ComfyUI และดึง URL รูปกลับมาเป็นลิสต์
    คืน dict: {"image_urls": [...], "seed": <int>}
    """
    payload = build_prompt_graph(
        model_name=model_name,
        positive=positive or "",
        negative=negative or "",
        seed=seed,
        width=width,
        height=height,
        n_images=n_images or 1,
    )

    resp = _post_json(f"{COMFY_HOST}/prompt", payload, timeout=90)
    prompt_id = resp.get("prompt_id") or resp.get("promptId")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return prompt_id: {resp}")

    hist = _poll_history(prompt_id, max_secs=300, sleep_secs=1.0)
    outputs = hist[prompt_id].get("outputs", {})

    # node 7 = SaveImage (ตาม workflows2.json)
    images = outputs.get("7", {}).get("images", [])
    image_urls = []
    for im in images or []:
        filename = im["filename"]
        subfolder = im.get("subfolder", "")
        image_urls.append(f"{COMFY_HOST}/view?filename={filename}&subfolder={subfolder}&type=output")

    if not image_urls:
        raise RuntimeError("No images found in ComfyUI outputs.")

    return {"image_urls": image_urls, "seed": payload["prompt"].get("4", {}).get("inputs", {}).get("seed")}


def generate_preview_frame(request):
    dimension_id = request.GET.get("dimension_id")
    batch = int(request.GET.get("batch", 1))

    try:
        dim = GenerateDimension.objects.get(id=dimension_id)
        raw = dim.value.replace("px", "").replace(" ", "")
        w, h = raw.split("x")
        width = int(w)
        height = int(h)
    except Exception:
        width = 1080
        height = 1080

    return render(request, "partials/preview_frame.html", {
        "batch_range": range(batch),
        "width": width,
        "height": height,
    })



@login_required(login_url='login')
@require_POST
def delete_history_view(request, pk):
    history = get_object_or_404(GenerateHistory, pk=pk)
    # Optional: check ownership
    if history.user != request.user:
        return JsonResponse({"status": "error", "message": "Ownership denied"}, status=403)
        
    history.delete()
    return JsonResponse({"status": "success"})








@login_required(login_url='login')





# ==========================================
# 2.3 ฟังก์ชันระบบ AI Agent
# ==========================================

@login_required(login_url='login')
@require_POST
def call_agent_view(request):
    topic = request.POST.get("topic", "").strip()
    prompts = call_agent(topic)
    return JsonResponse({
        "status": "success",
        "options": prompts
    })

@login_required(login_url='login')
@require_POST
def translate_prompt_view(request):
    text = request.POST.get("text", "").strip()
    if not text:
        return JsonResponse(
            {"status": "error", "message": "ไม่มีข้อความให้แปล"},
            status=400
        )

    en_prompt = translate_prompt_to_english(text)
    return JsonResponse({
        "status": "success",
        "prompt": en_prompt
    })

def call_agent(thai_prompt):
    try:
        template = f"""
You are a prompt generator for Stable Diffusion XL, optimized for novaOrangeXL_v90.
Your job is to turn the user's idea into 4 vivid and complete image-generation prompts.

STRICT RULES ABOUT FIDELITY:
- Detect the user’s language. If not Thai, translate to Thai.
- Use the Thai version as the canonical source.
- You MUST preserve the subject, scene, environment, objects, and actions exactly as the user describes.
- You MUST NOT remove the main content or output only metadata.

WHAT EACH PROMPT MUST CONTAIN:
- A full, detailed English sentence describing:
  • the subject  
  • appearance / clothing  
  • the scene and environment  
  • lighting  
  • action / pose  
  • atmosphere  
- The sentence MUST start with the subject.
- After the sentence, add the style tag in parentheses.

WHAT YOU MUST NOT DO:
- Do NOT drop or shorten the main description.
- Do NOT output prompts that only contain style, lighting, angle, or mood.
- Do NOT invent new characters or change the scene.

OUTPUT FORMAT:
- Create exactly 4 distinct prompts, numbered 1 to 4.
- Each prompt = 1 full English descriptive sentence + the metadata:
  (Artistic Style: ..., Lighting: ..., Camera Angle: ..., Mood: ...)

User input:
\"\"\"{thai_prompt}\"\"\"


Now follow these steps:
1) Translate the base user input into Thai (if not already Thai) and silently use it as the canonical base scene.
2) Identify missing components and expand the scene while preserving the core subject and environment.
3) Produce ONLY the 4 numbered prompts in English, nothing else.
"""


        result = subprocess.run(
            ["ollama", "run", "llama3.1", template],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300
        )

        output = result.stdout
        print("[Agent raw output]:\n", output)

        # จับบรรทัดที่ขึ้นต้นด้วยรูปแบบ 1), 2., 3-, 4:
        pattern = r'^\s*[1-4][\)\.\:\-]\s*(.*)'
        prompts = []

        for line in output.splitlines():
            m = re.match(pattern, line.strip())
            if m:
                prompts.append(m.group(1).strip().strip('" '))

        # ถ้าไม่มี prompt เลย → คืน list 1 รายการแทน ไม่คืน string!
        if len(prompts) == 0:
            return ["AI ไม่สามารถสร้าง prompt ได้"]

        # คืน list 4 รายการเสมอ
        return prompts[:4]

    except Exception as e:
        print("Agent Error:", e)
        return ["เกิดข้อผิดพลาดในการเรียก Agent"]

def translate_prompt_to_english(text: str) -> str:
    """
    ใช้ Ollama แปลข้อความให้เป็นภาษาอังกฤษ
    โดยสั่งให้ตอบออกมาเป็นประโยค Prompt ภาษาอังกฤษประโยคเดียว
    """
    try:
        template = f"""
You are a professional translator.
Translate the following THAI text into ENGLISH keywords/phrases for Stable Diffusion.

Input: "{text}"

INSTRUCTIONS:
1. Translate everything into ENGLISH.
2. Maintain the original meaning and details.
3. Use comma-separated phrases.
4. Output ONLY the English translation. NO explanations. NO Thai text in output.

Example:
Input: "แมวน่ารัก, บนอวกาศ"
Output: cute cat, in space

Output:
"""


        result = subprocess.run(
            ["ollama", "run", "llama3.1", template],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120
        )

        output = (result.stdout or "").strip()
        print("[Translate raw output]:\n", output)

        # กันเคสที่โมเดลตอบอะไรยาว ๆ มา มีหลายบรรทัด → เอาบรรทัดแรกพอ
        first_line = output.splitlines()[0].strip()
        return first_line

    except Exception as e:
        print("Translate Error:", e)
        return text  # ถ้าแปลพัง ให้คืนต้นฉบับกลับไป อย่างน้อยไม่ว่าง



def _extract_json_from_text(text):

    json_str = ""
    # 1. Try markdown code block (json optional)
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 2. Fallback: Find the *last* valid outer JSON block
        matches = re.findall(r'(\{.*?\})', text, re.DOTALL)
        if matches:
            # Prefer the last one as it's likely the final answer
            candidate = matches[-1]
            if '"subject"' in candidate:
                json_str = candidate
            else:
                # If last one is small, maybe it's the 1st one? Fallback range
                start_idx = text.find('{')
                end_idx = text.rfind('}') + 1
                if start_idx != -1 and end_idx != -1:
                    json_str = text[start_idx:end_idx]
        else:
             # Last resort
             start_idx = text.find('{')
             end_idx = text.rfind('}') + 1
             if start_idx != -1 and end_idx != -1:
                json_str = text[start_idx:end_idx]
    return json_str

def call_agent_assist(topic, style="", intended_subject=""):
    try:
        template = f"""
You are a creative AI assistant for image generation prompts.

User's Input: "{topic}"
User's Intended StyleTASK:
1. Analyze the "User's Input" (which can be in Thai or English).
2. Generate creative suggestions for each category to help build a detailed image prompt.
3. **OUTPUT MUST BE A VALID JSON OBJECT.**
4. **LANGUAGE RULE: Suggestions must match the language of the User's Input.** 
   - If Input is English -> Suggestions must be in English.
   - If Input is Thai -> Suggestions must be in Thai.

CRITICAL RULES:
- Keys must be English (e.g., "subject", "suggestions").
- Strings must use DOUBLE QUOTES (").
- **EXTRACTION RULE**: The "current" value must be COPIED EXACTLY from the Input. DO NOT TRANSLATE IT.
  - If Input says "Cat", "current" must be "Cat" (NOT "แมว").
  - If Input says "แมว", "current" must be "แมว".
- No extra text.

*** EXAMPLES ***

Example 1 (English Input -> English Output):
Input: "Cat"
Output:
{{
  "subject": {{ "current": "Cat", "suggestions": ["Cute cat", "Orange tabby", "Kitten", "Persian cat"] }},
  "action_pose": {{ "current": "", "suggestions": ["Sleeping", "Jumping", "Sitting by window", "Walking in garden"] }},
  "attributes": {{ "current": "", "suggestions": ["Fluffy fur", "Blue eyes", "Wearing collar", "Long tail"] }},
  "environment_setting": {{ "current": "", "suggestions": ["On a sofa", "In a living room", "On the roof", "In a cardboard box"] }},
  "composition_framing": {{ "current": "", "suggestions": ["Close-up shot", "Low angle", "Bokeh background", "Natural light"] }},
  "style": {{ "current": "", "suggestions": ["Photorealistic", "Watercolor painting", "Cartoon style", "3D Render"] }},
  "lighting": {{ "current": "", "suggestions": ["Morning sunlight", "Soft light", "Studio lighting", "Dark shadows"] }},
  "camera": {{ "current": "", "suggestions": ["Macro lens", "Wide angle", "Eye level", "High angle"] }},
  "mood": {{ "current": "", "suggestions": ["Cute and cheerful", "Warm", "Peaceful", "Playful"] }},
  "negative_prompt": {{ "current": "", "suggestions": ["Blurry image", "Cat with 5 legs", "Too dark", "Watermark"] }}
}}

Example 2 (Thai Input -> Thai Output):
Input: "หญิงสาว"
Output:
{{
  "subject": {{ "current": "หญิงสาว", "suggestions": ["สาวสวย", "ผู้หญิงวัยรุ่น", "นางแบบ", "สาวผมยาว"] }},
  "action_pose": {{ "current": "", "suggestions": ["ยืนยิ้ม", "เดินเล่น", "นั่งอ่านหนังสือ", "ถือดอกไม้"] }},
  "attributes": {{ "current": "", "suggestions": ["ผมสีทอง", "ตาสีฟ้า", "ใส่ชุดเดรส", "ผิวขาว"] }},
  "environment_setting": {{ "current": "", "suggestions": ["ในสวนดอกไม้", "ริมทะเล", "ในคาเฟ่", "บนถนนในเมือง"] }},
  "composition_framing": {{ "current": "", "suggestions": ["ภาพครึ่งตัว", "ภาพเต็มตัว", "หน้าชัดหลังเบลอ", "มุมสูง"] }},
  "style": {{ "current": "", "suggestions": ["ภาพถ่ายสมจริง", "ภาพวาดสีน้ำมัน", "สไตล์อนิเมะ", "ภาพแนวแฟนตาซี"] }},
  "lighting": {{ "current": "", "suggestions": ["แสงแดดยามเช้า", "แสงนวลตา", "แสงไฟสตูดิโอ", "เงามืด"] }},
  "camera": {{ "current": "", "suggestions": ["เลนส์มาโคร", "มุมกว้าง", "ระดับสายตา", "มุมสูง"] }},
  "mood": {{ "current": "", "suggestions": ["น่ารักสดใส", "อบอุ่น", "สงบ", "ขี้เล่น"] }},
  "negative_prompt": {{ "current": "", "suggestions": ["ภาพเบลอ", "แมวมี 5 ขา", "ภาพมืดเกินไป", "ลายน้ำ"] }}
}}

Output the JSON result for the following Input:
Input: "{topic}" (Style: "{style}", Subject: "{intended_subject}")
"""
        result = subprocess.run(
            ["ollama", "run", "llama3.1", template],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300
        )

        output = result.stdout.strip()
        print("[Agent Assist raw output]:\\n", output)
        
        json_str = _extract_json_from_text(output)

        # --- Self-Correction / Verification Loop ---
        if json_str:
            print("[Agent Assist]: verifying prompt...")
            verify_template = f"""
You are a Quality Assurance AI.
User Input: "{topic}"
Context: Style="{style}", Subject="{intended_subject}"

Generated JSON:
{json_str}

Check if the Generated JSON accurately reflects the User Input.
1. If it is GOOD and accurate, respond ONLY with the word: "USE"
2. If it is BAD or inaccurate, generate a NEW, CORRECTED JSON object.
"""
            try:
                verify_res = subprocess.run(
                    ["ollama", "run", "llama3.1", verify_template],
                    capture_output=True, text=True, encoding="utf-8", timeout=300
                )
                verify_out = verify_res.stdout.strip()
                print("[Agent Verification Output]:\\n", verify_out)
                
                # If response contains a JSON-like block, assume it's a correction
                if "{" in verify_out and "}" in verify_out:
                     corrected_json = _extract_json_from_text(verify_out)
                     if corrected_json:
                         print("[Agent Assist]: Using corrected JSON from verification.")
                         json_str = corrected_json
                elif "USE" in verify_out.upper():
                     print("[Agent Assist]: Prompt approved by verification.")
                else:
                     print("[Agent Assist]: Verification output ambiguous, keeping original.")
            except Exception as ve:
                print(f"[Agent Assist]: Verification failed: {ve}")
        # -------------------------------------------
        
        if json_str:
            try:
                data = json.loads(json_str)
                return data
            except json.JSONDecodeError as e:
                print(f"JSON Parse Error: {e}")
                # Log the extraction for debugging
                print(f"Extracted String: {json_str[:100]}...{json_str[-100:]}")
                return None
        else:
             print("No JSON structure found in output.")
             return None

    except Exception as e:
        print("Agent Assist Error:", e)
        return None

@login_required(login_url='login')
@require_POST
def call_agent_assist_view(request):
    topic = request.POST.get("topic", "").strip()
    style = request.POST.get("style", "").strip()
    intended_subject = request.POST.get("intended_subject", "").strip()
    
    data = call_agent_assist(topic, style, intended_subject)
    
    if data:
        return JsonResponse({
            "status": "success",
            "data": data
        })
    else:
        return JsonResponse({
            "status": "error",
            "message": "AI could not generate suggestions."
        })


# ==========================================
# 2.4 ฟังก์ชันโพสต์ / Community
# ==========================================

def post_feed_view(request):
    posts = Post.objects.all().order_by('-created_at')

    # แปลง queryset เป็น JSON
    data = []
    for post in posts:
        data.append({
            "id": post.id,
            "title": post.title or "",
            "caption": post.caption or "",
            "username": post.user.username,
            "profile_image": (
                post.user.profile.profile_image.url
                if hasattr(post.user, "profile") and post.user.profile.profile_image
                else None
            ),
            "created_since": timesince(post.created_at),
            "image": post.history.image_url if post.history else None,
            "likes_count": post.likes.count(),
            "comments_count": post.comments.count(),
            "is_liked": request.user in post.likes.all() if request.user.is_authenticated else False,
            "history_id": post.history.id if post.history else None,
            "prompt": post.history.positive_prompt if post.history else "",
            "negative": post.history.negative_prompt if post.history else "",
            "seed": post.history.seed if post.history else "",
            "model": post.history.model_name if post.history else "",
        })

    return render(request, 'post_feed.html', {
        "posts": posts,                    # ใช้ render ฟีดปกติ
        "posts_json": json.dumps(data),    # ใช้ JS filter client-side
    })

def post_create_view(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.image = request.FILES['image']  # หากภาพถูกส่งมาด้วย
            post.save()
            form.save_m2m()
            prompt = form.cleaned_data['prompt']  # หรือจะใช้ post.prompt ถ้ามี field นี้
            # Extract tags and add relationship
            tags = extract_tags_from_prompt(prompt)
            post.tags.add(*tags)
            return redirect('post_feed')  # เปลี่ยนชื่อได้ตามระบบของคุณ
    else:
        form = PostForm()
    return render(request, 'post_create.html', {'form': form})

@login_required(login_url= 'login')
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if request.method == 'POST':
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            return redirect('user_profile', username=request.user.username)  # ✅ กลับไปหน้าโปรไฟล์หลังบันทึก
    else:
        form = PostForm(instance=post)

    return render(request, 'posts/edit_post.html', {
        'post': post,
        'form': form
    })


@login_required(login_url='login')
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if not (request.user == post.user or request.user.is_staff):
        messages.error(request, "คุณไม่มีสิทธิ์ลบโพสต์นี้")
        return redirect(request.META.get('HTTP_REFERER', 'post_feed'))

    if request.method == 'POST':
        post.delete()
        messages.success(request, 'ลบโพสต์เรียบร้อยแล้ว')
        return redirect(request.META.get('HTTP_REFERER', 'post_feed'))

    return redirect(request.META.get('HTTP_REFERER', 'post_feed'))

@login_required(login_url='login')
def share_post(request, history_id):
    history = get_object_or_404(GenerateHistory, pk=history_id)
    
    # Check permission: Owner OR linked to existing Post
    if history.user != request.user:
        if not Post.objects.filter(history=history).exists():
             # Option: return 403 or redirect
             messages.error(request, "คุณไม่มีสิทธิ์แชร์ภาพนี้")
             return redirect("post_feed")
    
    # Handle rating update from GET param
    rating_param = request.GET.get("rating")
    if rating_param:
        try:
            rating_val = int(rating_param)
            if 1 <= rating_val <= 5:
                history.rating = rating_val
                history.save(update_fields=["rating"])
        except ValueError:
            pass

    extracted_tags = extract_tags_from_prompt(history.positive_prompt)
    all_tags = Tag.objects.all()

    if request.method == "POST":
        title = request.POST.get("title", "")
        caption = request.POST.get("caption", "")
        model_used = request.POST.get("model_used", "")
        additional_tag_ids = request.POST.getlist("tags")

        post = Post.objects.create(
            user=request.user,
            history=history,
            title=title,
            caption=caption,
            model_used=model_used,
        )

        custom_tags = request.POST.get("custom_tags", "")
        tag_list = [t.strip() for t in custom_tags.split(',') if t.strip()]
        for tag_name in tag_list:
            tag_name = tag_name[:100]
            tag_obj, _ = Tag.objects.get_or_create(name=tag_name)
            post.tags.add(tag_obj)
        
        combined_tags = extracted_tags + list(Tag.objects.filter(id__in=additional_tag_ids))
        post.tags.set(combined_tags)
        post.save()

        messages.success(request, "แชร์โพสต์เรียบร้อยแล้ว")
        return redirect("generate")

    default_caption = f"โพสต์จากภาพที่ฉันสร้างด้วย Prompt: {history.positive_prompt}"
    return render(request, "share_post.html", {
        "history": history,
        "default_caption": default_caption,
        "extracted_tags": extracted_tags,
        "all_tags": all_tags.exclude(id__in=[tag.id for tag in extracted_tags]),
    })

@login_required(login_url= 'login')
def user_profile(request, username):
    user_profile = get_object_or_404(User, username=username)
    profile = user_profile.profile
    posts = Post.objects.filter(user=user_profile).order_by('-created_at')  # แก้ตรงนี้
    return render(request, 'accounts/user_profile.html', {
        'user_profile': user_profile,
        'profile': profile,
        'posts': posts,
    })


def post_detail(request, post_id):
    post = Post.objects.get(id=post_id)
    comments = Comment.objects.filter(post=post).order_by('-created_at')

    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        data = json.loads(request.body)
        text = data.get("text")

        if text:
            comment = Comment.objects.create(post=post, user=request.user, text=text)
            return JsonResponse({
                "text": comment.text,
                "username": comment.user.username
            })
        else:
            return JsonResponse({"error": "ข้อความว่าง"}, status=400)

    return render(request, "posts/post_detail.html", {
        "post": post,
        "comments": comments,
    })
    
def comment_modal(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    comments = post.comments.all().order_by('-created_at')
    form = CommentForm()

    return render(request, 'posts/comment_modal.html', {
        'post': post,
        'comments': comments,
        'form': form,
    })
    
def add_comment(request, post_id):
    if request.method == 'POST':
        post = get_object_or_404(Post, id=post_id)
        text = request.POST.get('text')

        if text:
            Comment.objects.create(
                post=post,
                user=request.user,
                text=text
            )

    # ✅ กลับไปหน้าเดิมหลังจากบันทึก (refresh แล้วแสดงคอมเมนต์ใหม่ได้เลย)
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    
    # Check permission
    if request.user != comment.user:
        messages.error(request, "คุณไม่มีสิทธิ์แก้ไขความคิดเห็นนี้")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    if request.method == 'POST':
        text = request.POST.get('text')
        if text:
            comment.text = text
            comment.save()
            messages.success(request, "แก้ไขความคิดเห็นเรียบร้อยแล้ว")
    
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    
    # Check permission (Owner or Staff)
    if not (request.user == comment.user or request.user.is_staff):
        messages.error(request, "คุณไม่มีสิทธิ์ลบความคิดเห็นนี้")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    if request.method == 'POST':
        comment.delete()
        messages.success(request, "ลบความคิดเห็นเรียบร้อยแล้ว")
    
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if request.user in post.likes.all():
        post.likes.remove(request.user)
        liked = False
    else:
        post.likes.add(request.user)
        liked = True
    return JsonResponse({'liked': liked, 'count': post.likes.count()})

def ajax_search_posts(request):
    query = request.GET.get("q", "")
    if query:
        posts = Post.objects.filter(
            Q(title__icontains=query) |
            Q(caption__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
    else:
        posts = Post.objects.none()

def extract_tags_from_prompt(prompt):
    """
    Extract tags from prompt.
    Supports:
    1. Parenthesized structured tags: (Subject: Cat, Style: Anime)
    2. Plain comma-separated tags: Cat, lying down, looking at something
    """
    if not prompt:
        return []

    # 1. Try to find content inside parentheses if it looks like structured tags
    match = re.search(r'\(([^)]*Style:.*)\)', prompt)
    if match:
        tag_text = match.group(1)
    else:
        # Fallback: Treat the whole prompt as comma-separated tags
        tag_text = prompt

    tag_items = re.split(r',\s*', tag_text)
    tags = []
    
    for item in tag_items:
        item = item.strip()
        if not item:
            continue
            
        if ':' in item:
            # Format "Category: Name"
            parts = item.split(':', 1)
            category = parts[0].strip()[:100]
            name = parts[1].strip()
        else:
            # Plain tag
            category = "General" 
            name = item
            
        if name:
            # Normalize name (optional: lowercase or title case?) 
            # Let's keep original case but strip
            name = name[:100]
            tag, _ = Tag.objects.get_or_create(name=name, defaults={'category': category})
            tags.append(tag)

    return tags

def test_extract_tags(request):
    tags = []
    prompt = ""
    error = None

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()

        if not prompt:
            error = "กรุณาใส่ Prompt ก่อนวิเคราะห์แท็ก"
        else:
            try:
                tags = extract_tags_from_prompt(prompt)
                if not tags:
                    error = "ไม่สามารถดึงแท็กจาก Prompt นี้ได้"
            except Exception as e:
                error = f"เกิดข้อผิดพลาดขณะวิเคราะห์แท็ก: {str(e)}"

    return render(request, "test_tags.html", {
        "prompt": prompt,
        "tags": tags,
        "error": error
    })




# ==========================================
# 3. ผู้ดูแลระบบ (Admin)
# ==========================================

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

# ==========================================
# 3.1 ฟังก์ชันจัดการผู้ใช้ (User Management)
# ==========================================

@admin_required
def custom_admin(request):
    filter_type = request.GET.get('filter')
    today = timezone.now().date()

    # หน้าแดชบอร์ดแอดมิน + รายชื่อสมาชิก
    title = "จัดการสมาชิก (Members)"
    if filter_type == 'active_today':
        users_qs = User.objects.filter(last_login__date=today).order_by('-last_login')
        title = f"จัดการสมาชิก (Active Today: {today})"
    elif filter_type == 'new_today':
        users_qs = User.objects.filter(date_joined__date=today).order_by('-date_joined')
        title = f"จัดการสมาชิก (New Today: {today})"
    else:
        users_qs = User.objects.all().order_by("-date_joined")
    
    paginator = Paginator(users_qs, 5) # Show 5 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        "users": page_obj, # Template iterates over this
        "page_obj": page_obj, # For pagination controls
        "current_filter": filter_type,
        "title": title
    }
    return render(request, "custom_admin.html", context)

@admin_required
@require_POST
def admin_add_user(request):
    username = request.POST.get('username')
    email = request.POST.get('email')
    password = request.POST.get('password')
    confirm_password = request.POST.get('confirm_password')

    # Basic validations
    if not (username and email and password and confirm_password):
        messages.error(request, "กรุณากรอกข้อมูลให้ครบถ้วน")
        return redirect('custom_admin')

    if password != confirm_password:
        messages.error(request, "รหัสผ่านไม่ตรงกัน")
        return redirect('custom_admin')

    if User.objects.filter(username=username).exists():
        messages.error(request, "Username นี้มีผู้ใช้งานแล้ว")
        return redirect('custom_admin')

    if User.objects.filter(email=email).exists():
        messages.error(request, "Email นี้มีผู้ใช้งานแล้ว")
        return redirect('custom_admin')
    
    # Password complexity check (simple)
    if len(password) < 8 or not any(char.isdigit() for char in password):
        messages.error(request, "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษรและมีตัวเลขผสม")
        return redirect('custom_admin')

    try:
        user = User.objects.create_user(username=username, email=email, password=password)
        # Profile is created via signals
        messages.success(request, f"สร้างสมาชิกใหม่ {username} สำเร็จแล้ว")
    except Exception as e:
        messages.error(request, f"เกิดข้อผิดพลาด: {e}")

    return redirect('custom_admin')

@admin_required
def admin_toggle_user_active(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้ปิดการใช้งานตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถปิดการใช้งานบัญชีของตัวเองได้")
        return redirect("custom_admin")

    user.is_active = not user.is_active
    user.save()
    messages.success(request, f"อัปเดตสถานะการใช้งานของ {user.username} แล้ว")
    return redirect("custom_admin")

@admin_required
def admin_toggle_user_staff(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้เปลี่ยนสิทธิ์ตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถเปลี่ยนสิทธิ์ของตัวเองได้")
        return redirect("custom_admin")

    user.is_staff = not user.is_staff
    user.save()

    if user.is_staff:
        msg = f"ให้สิทธิ์แอดมินกับ {user.username} แล้ว"
    else:
        msg = f"ถอนสิทธิ์แอดมินของ {user.username} แล้ว"
    messages.success(request, msg)
    return redirect("custom_admin")

@admin_required
def admin_delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้ลบตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถลบบัญชีของตัวเองได้")
        return redirect("custom_admin")

    username = user.username
    user.delete()
    messages.success(request, f"ลบบัญชีผู้ใช้ {username} เรียบร้อยแล้ว")
    return redirect("custom_admin")


# ==========================================
# 3.2 ฟังก์ชันจัดการการสร้างภาพ (Models & Settings)
# ==========================================

@staff_required
def custom_model(request):
    models_qs = GenerateModel.objects.all().order_by("id")
    paginator = Paginator(models_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "custom_model.html", {
        "models_data": page_obj,
        "page_obj": page_obj,
    })

@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        # Note: models_available, dimensions etc. from deprecated Settings model?
        # Assuming we just need name/value/is_active for GenerateModel
        # But looking at previous code, there were two add_model versions.
        # One used GenerateSetting, one GenerateModel.
        # I will use the GenerateModel one as it matches the other CRUD functions.
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not name or not value:
            messages.error(request, "กรุณากรอกทั้ง Name และ Value")
            return redirect("custom_model")

        GenerateModel.objects.create(
            name=name,
            value=value,
            is_active=is_active
        )
        return redirect("custom_model")
    return redirect("custom_model")

def edit_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    if request.method == "POST":
        model.name = request.POST.get("name")
        model.value = request.POST.get("value")
        model.is_active = request.POST.get("is_active") == "true"
        model.save()
        messages.success(request, f"แก้ไข Model '{model.name}' สำเร็จแล้ว")
    return redirect("custom_model")

@staff_required
def delete_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    model_name = model.name
    model.delete()
    messages.success(request, f"ลบโมเดล '{model_name}' สำเร็จแล้ว")
    return redirect("custom_model")

def toggle_status(request, pk):
    model = GenerateModel.objects.get(pk=pk)
    model.is_active = not model.is_active
    model.save()
    return redirect("custom_model")

def custom_dimension(request):
    dimensions_qs = GenerateDimension.objects.all().order_by("id")
    paginator = Paginator(dimensions_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        "dimensions": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_dimension.html", context)

def add_dimension(request):
    if request.method == "POST":
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not label or not value:
            messages.error(request, "กรุณากรอก Label และ Value ให้ครบ")
            return redirect("custom_dimension")

        GenerateDimension.objects.create(label=label, value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Dimension '{label}' ({value}) สำเร็จแล้ว")
    return redirect("custom_dimension")

def edit_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    if request.method == "POST":
        dim.label = request.POST.get("label")
        dim.value = request.POST.get("value")
        dim.is_active = request.POST.get("is_active") == "true"
        dim.save()
        messages.success(request, f"แก้ไข Dimension '{dim.label}' สำเร็จแล้ว")
        return redirect("custom_dimension")
    return render(request, "edit_dimension.html", {"dimension": dim})

def delete_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.delete()
    messages.success(request, f"ลบ Dimension '{dim.label}' สำเร็จแล้ว")
    return redirect("custom_dimension")

def toggle_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.is_active = not dim.is_active
    dim.save()
    state = "Active" if dim.is_active else "Suspended"
    messages.success(request, f"Dimension '{dim.label}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_dimension")


def custom_count(request):
    counts_qs = GenerateCount.objects.all().order_by("id")
    paginator = Paginator(counts_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        "counts": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_count.html", context)

def add_count(request):
    if request.method == "POST":
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not value:
            messages.error(request, "กรุณากรอก Value")
            return redirect("custom_count")
        GenerateCount.objects.create(value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Count '{value}' สำเร็จแล้ว")
    return redirect("custom_count")

def edit_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    if request.method == "POST":
        count.value = request.POST.get("value")
        count.is_active = request.POST.get("is_active") == "true"
        count.save()
        messages.success(request, f"แก้ไข Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def delete_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.delete()
    messages.success(request, f"ลบ Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def toggle_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.is_active = not count.is_active
    count.save()
    state = "Active" if count.is_active else "Suspended"
    messages.success(request, f"Count '{count.value}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_count")


# helper
def _get_presets():
    setting = GenerateSetting.objects.first()
    if not setting:
        return {
            "models_available": [{"label": "Nova XL v9.0", "value": "novaOrangeXL_v90.safetensors"}],
            "dimensions": ["2:3", "1:1", "16:9"],
            "sizes": ["Small", "Medium", "Large"],
            "numbers": ["1", "2", "3", "4"],
            "defaults": {"model":"novaOrangeXL_v90.safetensors","dim":"2:3","size":"Small","count":"1"},
            "size_px_map": {"Small":512,"Medium":768,"Large":1024},
        }
    return {
        "models_available": [m.strip() for m in setting.models_available.split(",")],
        "dimensions": [d.strip() for d in setting.dimensions.split(",")],
        "sizes": [s.strip() for s in setting.sizes.split(",")],
        "numbers": [n.strip() for n in setting.number_of_images.split(",")],
        "defaults": {"model": setting.name, "dim": "2:3", "size": "Small", "count": "1"},
        "size_px_map": {"Small":512,"Medium":768,"Large":1024}
    }


# ==========================================
# 3.3 Dashboard Admin
# ==========================================

@admin_required
def dashboard_view(request):
    """
    Admin Dashboard: Overview of system statistics.
    Detailed version (Main).
    """
    today = timezone.now().date()
    
    # Basic Counters
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    total_comments = Comment.objects.count()
    total_generated_images = GenerateHistory.objects.count()

    # Activity Monitoring
    active_users_today = User.objects.filter(last_login__date=today).count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    generated_today = GenerateHistory.objects.filter(created_at__date=today).count()
    active_models = GenerateModel.objects.filter(is_active=True).count()
    tags_count = Tag.objects.count()

    # Recent Data
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_images = GenerateHistory.objects.select_related('user').order_by('-created_at')[:5]

    # Model Usage Stats
    model_usage_data = GenerateHistory.objects.values('model_name').annotate(count=Count('model_name')).order_by('-count')[:5]
    model_usage = []
    if total_generated_images > 0:
        for m in model_usage_data:
            percent = (m['count'] / total_generated_images) * 100
            model_usage.append({
                'model_name': m['model_name'],
                'count': m['count'],
                'percent': round(percent, 1)
            })

    # Tag Usage Stats
    tag_usage = Tag.objects.annotate(count=Count('posts')).order_by('-count')[:5]

    context = {
        "total_users": total_users,
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_generated_images": total_generated_images,
        "active_users_today": active_users_today,
        "new_users_today": new_users_today,
        "generated_today": generated_today,
        "active_models": active_models,
        "tags_count": tags_count,
        "recent_users": recent_users,
        "recent_images": recent_images,
        "model_usage": model_usage,
        "tag_usage": tag_usage,
    }
    return render(request, "dashboard.html", context)


@admin_required
def admin_dashboard(request):
    """
    Legacy Admin Dashboard
    """
    today = timezone.now().date()
    
    total_users = User.objects.count()
    active_users_today = User.objects.filter(last_login__date=today).count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    active_models = GenerateModel.objects.filter(is_active=True).count()
    tags_count = Tag.objects.count()
    total_generated_images = GenerateHistory.objects.count()
    generated_today = GenerateHistory.objects.filter(created_at__date=today).count()

    recent_users = User.objects.order_by("-date_joined")[:5]
    recent_images = GenerateHistory.objects.select_related('user').order_by('-created_at')[:5]
    
    model_usage = GenerateModel.objects.annotate(count=Count('generatehistory')).order_by('-count')[:5]
    tag_usage = Tag.objects.annotate(count=Count('posts')).order_by('-count')[:5]

    return render(request, "dashboard.html", {
        "total_users": total_users,
        "active_users_today": active_users_today,
        "new_users_today": new_users_today,
        "recent_users": recent_users,
        "recent_images": recent_images,
        "total_generated_images": total_generated_images,
        "generated_today": generated_today,
        "active_models": active_models,
        "tags_count": tags_count,
        "model_usage": model_usage,
        "tag_usage": tag_usage,
    })


@admin_required
def ajax_dashboard_widget(request):
    """
    API for Load More functionality on dashboard widgets.
    Params: widget_type, offset, limit (default 5)
    """
    widget_type = request.GET.get('widget_type')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 5))
    
    data = []
    has_more = False
    
    if widget_type == 'images':
        qs = GenerateHistory.objects.select_related('user').order_by('-created_at')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        for img in items:
            data.append({
                'user': img.user.username,
                'model_name': img.model_name,
                'positive_prompt': img.positive_prompt,
                'seed': img.seed,
                'time': timesince(img.created_at) + " ago",
            })
            
    elif widget_type == 'users':
        qs = User.objects.all().order_by('-date_joined')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        for u in items:
            data.append({
                'username': u.username,
                'email': u.email if u.email else "-",
                'joined': u.date_joined.strftime("%d/%m/%Y")
            })
            
    elif widget_type == 'models':
        qs = GenerateHistory.objects.values('model_name').annotate(count=Count('model_name')).order_by('-count')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        for m in items:
            data.append({
                'model_name': m['model_name'],
                'count': m['count']
            })
            
    elif widget_type == 'tags':
        qs = Tag.objects.annotate(count=Count('posts')).order_by('-count')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        for t in items:
            data.append({
                'name': t.name,
                'count': t.count
            })
            
    return JsonResponse({
        "status": "success",
        "data": data,
        "has_more": has_more
    })

@admin_required
def admin_post_list(request):
    posts = Post.objects.select_related('user').order_by('-created_at')
    rows = []
    for p in posts:
        image_html = f'<img src="{p.history.image_url}" class="w-10 h-10 object-cover rounded">' if p.history and p.history.image_url else "-"
        rows.append({
            'id': p.id,
            'data': [
                image_html,
                p.title or "(No Title)",
                p.user.username,
                p.created_at.strftime("%Y-%m-%d %H:%M")
            ]
        })
    return render(request, "admin_data_list.html", {
        "title": "Manage Posts",
        "headers": ["Image", "Title", "Owner", "Created At"],
        "rows": rows,
        "delete_url_name": "admin_delete_post"
    })

@admin_required
@require_POST
def admin_delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.delete()
    messages.success(request, "Post deleted successfully.")
    return redirect('admin_post_list')

@admin_required
def admin_comment_list(request):
    comments = Comment.objects.select_related('user', 'post').order_by('-created_at')
    rows = []
    for c in comments:
        rows.append({
            'id': c.id,
            'data': [
                c.text[:50] + "..." if len(c.text) > 50 else c.text,
                c.user.username,
                f"Post #{c.post.id}",
                c.created_at.strftime("%Y-%m-%d %H:%M")
            ]
        })
    return render(request, "admin_data_list.html", {
        "title": "Manage Comments",
        "headers": ["Comment", "User", "Post", "Date"],
        "rows": rows,
        "delete_url_name": "admin_delete_comment"
    })

@admin_required
@require_POST
def admin_delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    comment.delete()
    messages.success(request, "Comment deleted successfully.")
    return redirect('admin_comment_list')

@admin_required
def admin_image_list(request):
    filter_type = request.GET.get('filter')
    today = timezone.now().date()
    
    if filter_type == 'today':
        images = GenerateHistory.objects.filter(created_at__date=today).select_related('user').order_by('-created_at')
        title = f"ภาพที่สร้างวันนี้ (Today: {today})"
    else:
        images = GenerateHistory.objects.select_related('user').order_by('-created_at')
        title = "จัดการรูปภาพที่สร้าง (All Generated Images)"
    rows = []
    for img in images:
        image_html = f'<img src="{img.image_url}" class="w-10 h-10 object-cover rounded">'
        rows.append({
            'id': img.id,
            'data': [
                image_html,
                img.positive_prompt[:50] + "...",
                img.user.username,
                img.model_name
            ]
        })
    return render(request, "admin_data_list.html", {
        "title": title,
        "headers": ["Image", "Prompt", "User", "Model"],
        "rows": rows,
        "delete_url_name": "admin_delete_image"
    })

@admin_required
@require_POST
def admin_delete_image(request, pk):
    img = get_object_or_404(GenerateHistory, pk=pk)
    img.delete()
    messages.success(request, "Image history deleted successfully.")
    return redirect('admin_image_list')

@admin_required
def admin_tag_list(request):
    sort_param = request.GET.get('sort')
    tags_qs = Tag.objects.annotate(usage_count=Count('posts'))
    
    if sort_param == 'usage_asc':
        tags_qs = tags_qs.order_by('usage_count')
    elif sort_param == 'usage_desc':
        tags_qs = tags_qs.order_by('-usage_count')
    else:
        tags_qs = tags_qs.order_by('category', 'name')
        
    paginator = Paginator(tags_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        "tags": page_obj,
        "page_obj": page_obj,
        "current_sort": sort_param
    }
    return render(request, "admin_tag_list.html", context)

@admin_required
@require_POST
def admin_add_tag(request):
    name = request.POST.get("name")
    category = request.POST.get("category", "Uncategorized")
    
    if name:
        name = name[:100]
        category = category[:100]
        Tag.objects.create(name=name, category=category)
        messages.success(request, f"เพิ่ม Tag '{name}' สำเร็จแล้ว")
    else:
        messages.error(request, "กรุณาระบุชื่อ Tag")
        
    return redirect("admin_tag_list")

@admin_required
@require_POST
def admin_edit_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    name = request.POST.get("name")
    category = request.POST.get("category", "Uncategorized")
    
    if name:
        tag.name = name[:100]
        tag.category = category[:100]
        tag.save()
        messages.success(request, f"แก้ไข Tag '{name}' สำเร็จแล้ว")
    else:
        messages.error(request, "กรุณาระบุชื่อ Tag")
        
    return redirect("admin_tag_list")

@admin_required
@require_POST
def admin_delete_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    tag.delete()
    messages.success(request, "Tag deleted successfully.")
    return redirect('admin_tag_list')

def dashboard_view(request):
    """
    Admin Dashboard: Overview of system statistics.
    Legacy version with detailed metrics.
    """

    today = timezone.now().date()
    
    # Basic Counters
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    total_comments = Comment.objects.count()
    total_generated_images = GenerateHistory.objects.count()

    # Activity Monitoring
    active_users_today = User.objects.filter(last_login__date=today).count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    generated_today = GenerateHistory.objects.filter(created_at__date=today).count()
    active_models = GenerateModel.objects.filter(is_active=True).count()
    tags_count = Tag.objects.count()

    # Recent Data
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_images = GenerateHistory.objects.select_related('user').order_by('-created_at')[:5]

    # Model Usage Stats
    model_usage_data = GenerateHistory.objects.values('model_name').annotate(count=Count('model_name')).order_by('-count')[:5]
    # Calculate percentages
    model_usage = []
    if total_generated_images > 0:
        for m in model_usage_data:
            percent = (m['count'] / total_generated_images) * 100
            model_usage.append({
                'model_name': m['model_name'],
                'count': m['count'],
                'percent': round(percent, 1)
            })

    # Tag Usage Stats
    tag_usage = Tag.objects.annotate(count=Count('posts')).order_by('-count')[:5]

    context = {
        "total_users": total_users,
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_generated_images": total_generated_images,
        "active_users_today": active_users_today,
        "new_users_today": new_users_today,
        "generated_today": generated_today,
        "active_models": active_models,
        "tags_count": tags_count,
        "recent_users": recent_users,
        "recent_images": recent_images,
        "model_usage": model_usage,
        "tag_usage": tag_usage,
    }
    return render(request, "dashboard.html", context)

@admin_required
def ajax_dashboard_widget(request):
    """
    API for Load More functionality on dashboard widgets.
    Params: widget_type, offset, limit (default 5)
    """
    
    widget_type = request.GET.get('widget_type')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 5))
    
    data = []
    has_more = False
    
    if widget_type == 'images':
        # Fetch images
        qs = GenerateHistory.objects.select_related('user').order_by('-created_at')
        total = qs.count()
        # Slicing
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        
        for img in items:
            data.append({
                'user': img.user.username,
                'model_name': img.model_name,
                'positive_prompt': img.positive_prompt,
                'seed': img.seed,
                'time': timesince(img.created_at) + " ago",
            })
            
    elif widget_type == 'users':
        qs = User.objects.all().order_by('-date_joined')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        
        for u in items:
            data.append({
                'username': u.username,
                'email': u.email if u.email else "-",
                'joined': u.date_joined.strftime("%d/%m/%Y")
            })
            
    elif widget_type == 'models':
        # Aggregation is tricky with offset if we want "most used".
        qs = GenerateHistory.objects.values('model_name').annotate(count=Count('model_name')).order_by('-count')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        
        for m in items:
            data.append({
                'model_name': m['model_name'],
                'count': m['count']
            })
            
    elif widget_type == 'tags':
        qs = Tag.objects.annotate(count=Count('posts')).order_by('-count')
        total = qs.count()
        items = qs[offset : offset + limit]
        has_more = (offset + limit) < total
        
        for t in items:
            data.append({
                'name': t.name,
                'count': t.count
            })
            
    return JsonResponse({
        "status": "success",
        "data": data,
        "has_more": has_more
    })

# ==========================================
# 3.2 จัดการสมาชิก (User Management)
# ==========================================

@admin_required
def custom_admin(request):
    filter_type = request.GET.get('filter')
    today = timezone.now().date()

    # หน้าแดชบอร์ดแอดมิน + รายชื่อสมาชิก
    title = "จัดการสมาชิก (Members)"
    if filter_type == 'active_today':
        users_qs = User.objects.filter(last_login__date=today).order_by('-last_login')
        title = f"จัดการสมาชิก (Active Today: {today})"
    elif filter_type == 'new_today':
        users_qs = User.objects.filter(date_joined__date=today).order_by('-date_joined')
        title = f"จัดการสมาชิก (New Today: {today})"
    else:
        users_qs = User.objects.all().order_by("-date_joined")
    
    paginator = Paginator(users_qs, 5) # Show 5 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        "users": page_obj, # Template iterates over this
        "page_obj": page_obj, # For pagination controls
        "current_filter": filter_type,
        "title": title
    }
    return render(request, "custom_admin.html", context)

@admin_required
@require_POST
def admin_add_user(request):
    username = request.POST.get('username')
    email = request.POST.get('email')
    password = request.POST.get('password')
    confirm_password = request.POST.get('confirm_password')

    # Basic validations
    if not (username and email and password and confirm_password):
        messages.error(request, "กรุณากรอกข้อมูลให้ครบถ้วน")
        return redirect('custom_admin')

    if password != confirm_password:
        messages.error(request, "รหัสผ่านไม่ตรงกัน")
        return redirect('custom_admin')

    if User.objects.filter(username=username).exists():
        messages.error(request, "Username นี้มีผู้ใช้งานแล้ว")
        return redirect('custom_admin')

    if User.objects.filter(email=email).exists():
        messages.error(request, "Email นี้มีผู้ใช้งานแล้ว")
        return redirect('custom_admin')
    
    # Password complexity check (simple)
    if len(password) < 8 or not any(char.isdigit() for char in password):
        messages.error(request, "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษรและมีตัวเลขผสม")
        return redirect('custom_admin')

    try:
        user = User.objects.create_user(username=username, email=email, password=password)
        # Profile is created via signals
        messages.success(request, f"สร้างสมาชิกใหม่ {username} สำเร็จแล้ว")
    except Exception as e:
        messages.error(request, f"เกิดข้อผิดพลาด: {e}")

    return redirect('custom_admin')

@admin_required
def admin_toggle_user_active(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้ปิดการใช้งานตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถปิดการใช้งานบัญชีของตัวเองได้")
        return redirect("custom_admin")

    user.is_active = not user.is_active
    user.save()
    messages.success(request, f"อัปเดตสถานะการใช้งานของ {user.username} แล้ว")
    return redirect("custom_admin")

@admin_required
def admin_toggle_user_staff(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้เปลี่ยนสิทธิ์ตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถเปลี่ยนสิทธิ์ของตัวเองได้")
        return redirect("custom_admin")

    user.is_staff = not user.is_staff
    user.save()

    if user.is_staff:
        msg = f"ให้สิทธิ์แอดมินกับ {user.username} แล้ว"
    else:
        msg = f"ถอนสิทธิ์แอดมินของ {user.username} แล้ว"
    messages.success(request, msg)
    return redirect("custom_admin")

@admin_required
def admin_delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้ลบตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถลบบัญชีของตัวเองได้")
        return redirect("custom_admin")

    username = user.username
    user.delete()
    messages.success(request, f"ลบบัญชีผู้ใช้ {username} เรียบร้อยแล้ว")
    return redirect("custom_admin")

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

# ==========================================
# 3.3 จัดการ Model (Model Management)
# ==========================================

@staff_required
def custom_model(request):
    models_qs = GenerateModel.objects.all().order_by("id")
    paginator = Paginator(models_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "custom_model.html", {
        "models_data": page_obj,
        "page_obj": page_obj,
    })

@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not name or not value:
            messages.error(request, "กรุณากรอกทั้ง Name และ Value")
            return redirect("custom_model")

        GenerateModel.objects.create(
            name=name,
            value=value,
            is_active=is_active
        )
        return redirect("custom_model")

def edit_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    if request.method == "POST":
        model.name = request.POST.get("name")
        model.value = request.POST.get("value")
        model.is_active = request.POST.get("is_active") == "true"
        model.save()
        messages.success(request, f"แก้ไข Model '{model.name}' สำเร็จแล้ว")
    return redirect("custom_model")

@staff_required
def delete_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    model_name = model.name
    model.delete()
    messages.success(request, f"ลบโมเดล '{model_name}' สำเร็จแล้ว")
    return redirect("custom_model")

def toggle_status(request, pk):
    model = GenerateModel.objects.get(pk=pk)
    model.is_active = not model.is_active
    model.save()
    return redirect("custom_model")

def _get_presets():
    # Helper for getting presets (possibly deprecated if not used)
    setting = GenerateSetting.objects.first()
    if not setting:
        return {
            "models_available": [{"label": "Nova XL v9.0", "value": "novaOrangeXL_v90.safetensors"}],
            "dimensions": ["2:3", "1:1", "16:9"],
            "sizes": ["Small", "Medium", "Large"],
            "numbers": ["1", "2", "3", "4"],
            "defaults": {"model":"novaOrangeXL_v90.safetensors","dim":"2:3","size":"Small","count":"1"},
            "size_px_map": {"Small":512,"Medium":768,"Large":1024},
        }
    return {
        "models_available": [m.strip() for m in setting.models_available.split(",")],
        "dimensions": [d.strip() for d in setting.dimensions.split(",")],
        "sizes": [s.strip() for s in setting.sizes.split(",")],
        "numbers": [n.strip() for n in setting.number_of_images.split(",")],
        "defaults": {"model": setting.name, "dim": "2:3", "size": "Small", "count": "1"},
        "size_px_map": {"Small":512,"Medium":768,"Large":1024}
    }

# ==========================================
# 3.4 จัดการ Dimension (Dimension Management)
# ==========================================

def custom_dimension(request):
    dimensions_qs = GenerateDimension.objects.all().order_by("id")
    paginator = Paginator(dimensions_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        "dimensions": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_dimension.html", context)

def add_dimension(request):
    if request.method == "POST":
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not label or not value:
            messages.error(request, "กรุณากรอก Label และ Value ให้ครบ")
            return redirect("custom_dimension")

        GenerateDimension.objects.create(label=label, value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Dimension '{label}' ({value}) สำเร็จแล้ว")
    return redirect("custom_dimension")

def edit_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    if request.method == "POST":
        dim.label = request.POST.get("label")
        dim.value = request.POST.get("value")
        dim.is_active = request.POST.get("is_active") == "true"
        dim.save()
        messages.success(request, f"แก้ไข Dimension '{dim.label}' สำเร็จแล้ว")
        return redirect("custom_dimension")
    return render(request, "edit_dimension.html", {"dimension": dim})

def delete_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.delete()
    messages.success(request, f"ลบ Dimension '{dim.label}' สำเร็จแล้ว")
    return redirect("custom_dimension")

def toggle_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.is_active = not dim.is_active
    dim.save()
    state = "Active" if dim.is_active else "Suspended"
    messages.success(request, f"Dimension '{dim.label}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_dimension")

# ==========================================
# 3.5 จัดการ Count (Count Management)
# ==========================================

def custom_count(request):
    counts_qs = GenerateCount.objects.all().order_by("id")
    paginator = Paginator(counts_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        "counts": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_count.html", context)

def add_count(request):
    if request.method == "POST":
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not value:
            messages.error(request, "กรุณากรอก Value")
            return redirect("custom_count")
        GenerateCount.objects.create(value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Count '{value}' สำเร็จแล้ว")
    return redirect("custom_count")

def edit_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    if request.method == "POST":
        count.value = request.POST.get("value")
        count.is_active = request.POST.get("is_active") == "true"
        count.save()
        messages.success(request, f"แก้ไข Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def delete_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.delete()
    messages.success(request, f"ลบ Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def toggle_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.is_active = not count.is_active
    count.save()
    state = "Active" if count.is_active else "Suspended"
    messages.success(request, f"Count '{count.value}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_count")



@admin_required
def admin_dashboard(request):
    today = timezone.now().date()
    
    # สถิติจริงจาก User
    total_users = User.objects.count()
    active_users_today = User.objects.filter(last_login__date=today).count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    
    # Models, Tags, Images Count (Real queries)
    active_models = GenerateModel.objects.filter(is_active=True).count()
    tags_count = Tag.objects.count()
    
    # Use real GenerateHistory count if available, else 0
    total_generated_images = GenerateHistory.objects.count()
    generated_today = GenerateHistory.objects.filter(created_at__date=today).count()

    # สมาชิกใหม่ล่าสุด (5 คน)
    recent_users = User.objects.order_by("-date_joined")[:5]
    
    # ภาพที่สร้างล่าสุด (5 ภาพ)
    recent_images = GenerateHistory.objects.select_related('user').order_by('-created_at')[:5]
    
    # Model Usage (Top 5)
    model_usage = GenerateModel.objects.annotate(count=Count('generatehistory')).order_by('-count')[:5]
    
    # Tag Usage (Top 5)
    tag_usage = Tag.objects.annotate(count=Count('posts')).order_by('-count')[:5]

    return render(request, "dashboard.html", {
        "total_users": total_users,
        "active_users_today": active_users_today,
        "new_users_today": new_users_today,
        "recent_users": recent_users,
        "recent_images": recent_images,
        "total_generated_images": total_generated_images,
        "generated_today": generated_today,
        "active_models": active_models,
        "tags_count": tags_count,
        "model_usage": model_usage,
        "tag_usage": tag_usage,
    })

    # ตัวอย่างการใช้งานโมเดล (dummy)
    model_usage = [
        {"name": "sdxl", "percent": 50},
        {"name": "anime-v1", "percent": 30},
        {"name": "nova", "percent": 20},
    ]

    # ตัวอย่างการใช้งานแท็ก (dummy)
    tag_usage = [
        {"name": "cinematic lighting", "count": 42},
        {"name": "soft light", "count": 35},
        {"name": "portrait", "count": 28},
        {"name": "wide shot", "count": 19},
    ]

    context = {
        "total_users": total_users,
        "active_users_today": active_users_today,
        "new_users_today": new_users_today,
        "total_generated_images": total_generated_images,
        "generated_today": generated_today,
        "active_models": active_models,
        "tags_count": tags_count,
        "recent_users": recent_users,
        "recent_images": recent_images,
        "model_usage": model_usage,
        "tag_usage": tag_usage,
    }
    return render(request, "dashboard.html", context)

@admin_required
def custom_admin(request):

    
    filter_type = request.GET.get('filter')
    today = timezone.now().date()

    # หน้าแดชบอร์ดแอดมิน + รายชื่อสมาชิก
    title = "จัดการสมาชิก (Members)"
    if filter_type == 'active_today':
        users_qs = User.objects.filter(last_login__date=today).order_by('-last_login')
        title = f"จัดการสมาชิก (Active Today: {today})"
    elif filter_type == 'new_today':
        users_qs = User.objects.filter(date_joined__date=today).order_by('-date_joined')
        title = f"จัดการสมาชิก (New Today: {today})"
    else:
        users_qs = User.objects.all().order_by("-date_joined")
    
    paginator = Paginator(users_qs, 5) # Show 5 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        "users": page_obj, # Template iterates over this
        "page_obj": page_obj, # For pagination controls
        "current_filter": filter_type,
        "title": title
    }
    return render(request, "custom_admin.html", context)


@admin_required
def admin_toggle_user_active(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้ปิดการใช้งานตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถปิดการใช้งานบัญชีของตัวเองได้")
        return redirect("custom_admin")

    user.is_active = not user.is_active
    user.save()
    messages.success(request, f"อัปเดตสถานะการใช้งานของ {user.username} แล้ว")
    return redirect("custom_admin")


@admin_required
def admin_toggle_user_staff(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้เปลี่ยนสิทธิ์ตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถเปลี่ยนสิทธิ์ของตัวเองได้")
        return redirect("custom_admin")

    user.is_staff = not user.is_staff
    user.save()

    if user.is_staff:
        msg = f"ให้สิทธิ์แอดมินกับ {user.username} แล้ว"
    else:
        msg = f"ถอนสิทธิ์แอดมินของ {user.username} แล้ว"
    messages.success(request, msg)
    return redirect("custom_admin")


@admin_required
def admin_delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # กันไม่ให้ลบตัวเอง
    if request.user == user:
        messages.error(request, "ไม่สามารถลบบัญชีของตัวเองได้")
        return redirect("custom_admin")

    username = user.username
    user.delete()
    messages.success(request, f"ลบบัญชีผู้ใช้ {username} เรียบร้อยแล้ว")
    return redirect("custom_admin")


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

@staff_required
def custom_model(request):

    models_qs = GenerateModel.objects.all().order_by("id")
    
    paginator = Paginator(models_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "custom_model.html", {
        "models_data": page_obj,
        "page_obj": page_obj,
    })

@staff_required
def delete_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)  # ใช้ GenerateModel
    model_name = model.name                         # เก็บชื่อไว้ก่อนลบ
    model.delete()

    # ใช้ message framework เพื่อแสดงชื่อที่ถูกลบ

    messages.success(request, f"ลบโมเดล '{model_name}' สำเร็จแล้ว")

    return redirect("custom_model")


@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        models_available = request.POST.get("models_available")
        dimensions = request.POST.get("dimensions")
        sizes = request.POST.get("sizes")
        number_of_images = request.POST.get("number_of_images")

        GenerateSetting.objects.create(
            name=name,
            models_available=models_available,
            dimensions=dimensions,
            sizes=sizes,
            number_of_images=number_of_images,
        )
        return redirect("custom_model")

    return redirect("custom_model")

def edit_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    if request.method == "POST":
        model.name = request.POST.get("name")
        model.value = request.POST.get("value")
        model.is_active = request.POST.get("is_active") == "true"
        model.save()
        messages.success(request, f"แก้ไข Model '{model.name}' สำเร็จแล้ว")
    return redirect("custom_model")


def toggle_status(request, pk):
    model = GenerateModel.objects.get(pk=pk)
    model.is_active = not model.is_active   # ใช้ฟิลด์ is_active แทน status
    model.save()
    return redirect("custom_model")

@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not name or not value:
            messages.error(request, "กรุณากรอกทั้ง Name และ Value")
            return redirect("custom_model")

        GenerateModel.objects.create(
            name=name,
            value=value,
            is_active=is_active
        )
        return redirect("custom_model")




# helper
def _get_presets():
    setting = GenerateSetting.objects.first()
    if not setting:
        return {
            "models_available": [{"label": "Nova XL v9.0", "value": "novaOrangeXL_v90.safetensors"}],
            "dimensions": ["2:3", "1:1", "16:9"],
            "sizes": ["Small", "Medium", "Large"],
            "numbers": ["1", "2", "3", "4"],
            "defaults": {"model":"novaOrangeXL_v90.safetensors","dim":"2:3","size":"Small","count":"1"},
            "size_px_map": {"Small":512,"Medium":768,"Large":1024},
        }
    return {
        "models_available": [m.strip() for m in setting.models_available.split(",")],
        "dimensions": [d.strip() for d in setting.dimensions.split(",")],
        "sizes": [s.strip() for s in setting.sizes.split(",")],
        "numbers": [n.strip() for n in setting.number_of_images.split(",")],
        "defaults": {"model": setting.name, "dim": "2:3", "size": "Small", "count": "1"},
        "size_px_map": {"Small":512,"Medium":768,"Large":1024}
    }





def custom_dimension(request):

    dimensions_qs = GenerateDimension.objects.all().order_by("id")
    
    paginator = Paginator(dimensions_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        "dimensions": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_dimension.html", context)


def add_dimension(request):
    if request.method == "POST":
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not label or not value:
            messages.error(request, "กรุณากรอก Label และ Value ให้ครบ")
            return redirect("custom_dimension")

        GenerateDimension.objects.create(label=label, value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Dimension '{label}' ({value}) สำเร็จแล้ว")
    return redirect("custom_dimension")


def edit_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    if request.method == "POST":
        dim.label = request.POST.get("label")
        dim.value = request.POST.get("value")
        dim.is_active = request.POST.get("is_active") == "true"
        dim.save()
        messages.success(request, f"แก้ไข Dimension '{dim.label}' สำเร็จแล้ว")
        return redirect("custom_dimension")
    return render(request, "edit_dimension.html", {"dimension": dim})


def delete_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.delete()
    messages.success(request, f"ลบ Dimension '{dim.label}' สำเร็จแล้ว")
    return redirect("custom_dimension")


def toggle_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.is_active = not dim.is_active
    dim.save()
    state = "Active" if dim.is_active else "Suspended"
    messages.success(request, f"Dimension '{dim.label}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_dimension")


def custom_count(request):

    counts_qs = GenerateCount.objects.all().order_by("id")
    
    paginator = Paginator(counts_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        "counts": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_count.html", context)

def add_count(request):
    if request.method == "POST":
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not value:
            messages.error(request, "กรุณากรอก Value")
            return redirect("custom_count")
        GenerateCount.objects.create(value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Count '{value}' สำเร็จแล้ว")
    return redirect("custom_count")

def edit_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    if request.method == "POST":
        count.value = request.POST.get("value")
        count.is_active = request.POST.get("is_active") == "true"
        count.save()
        messages.success(request, f"แก้ไข Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def delete_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.delete()
    messages.success(request, f"ลบ Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def toggle_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.is_active = not count.is_active
    count.save()
    state = "Active" if count.is_active else "Suspended"
    messages.success(request, f"Count '{count.value}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_count")
    messages.success(request, f"ลบบัญชีผู้ใช้ {username} เรียบร้อยแล้ว")
    return redirect("custom_admin")


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

@staff_required
def custom_model(request):

    models_qs = GenerateModel.objects.all().order_by("id")
    
    paginator = Paginator(models_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "custom_model.html", {
        "models_data": page_obj,
        "page_obj": page_obj,
    })

@staff_required
def delete_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)  # ใช้ GenerateModel
    model_name = model.name                         # เก็บชื่อไว้ก่อนลบ
    model.delete()

    # ใช้ message framework เพื่อแสดงชื่อที่ถูกลบ

    messages.success(request, f"ลบโมเดล '{model_name}' สำเร็จแล้ว")

    return redirect("custom_model")


@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        models_available = request.POST.get("models_available")
        dimensions = request.POST.get("dimensions")
        sizes = request.POST.get("sizes")
        number_of_images = request.POST.get("number_of_images")

        GenerateSetting.objects.create(
            name=name,
            models_available=models_available,
            dimensions=dimensions,
            sizes=sizes,
            number_of_images=number_of_images,
        )
        return redirect("custom_model")

    return redirect("custom_model")

def edit_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    if request.method == "POST":
        model.name = request.POST.get("name")
        model.value = request.POST.get("value")
        model.is_active = request.POST.get("is_active") == "true"
        model.save()
        messages.success(request, f"แก้ไข Model '{model.name}' สำเร็จแล้ว")
    return redirect("custom_model")


def toggle_status(request, pk):
    model = GenerateModel.objects.get(pk=pk)
    model.is_active = not model.is_active   # ใช้ฟิลด์ is_active แทน status
    model.save()
    return redirect("custom_model")

@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not name or not value:
            messages.error(request, "กรุณากรอกทั้ง Name และ Value")
            return redirect("custom_model")

        GenerateModel.objects.create(
            name=name,
            value=value,
            is_active=is_active
        )
        return redirect("custom_model")




# helper
def _get_presets():
    setting = GenerateSetting.objects.first()
    if not setting:
        return {
            "models_available": [{"label": "Nova XL v9.0", "value": "novaOrangeXL_v90.safetensors"}],
            "dimensions": ["2:3", "1:1", "16:9"],
            "sizes": ["Small", "Medium", "Large"],
            "numbers": ["1", "2", "3", "4"],
            "defaults": {"model":"novaOrangeXL_v90.safetensors","dim":"2:3","size":"Small","count":"1"},
            "size_px_map": {"Small":512,"Medium":768,"Large":1024},
        }
    return {
        "models_available": [m.strip() for m in setting.models_available.split(",")],
        "dimensions": [d.strip() for d in setting.dimensions.split(",")],
        "sizes": [s.strip() for s in setting.sizes.split(",")],
        "numbers": [n.strip() for n in setting.number_of_images.split(",")],
        "defaults": {"model": setting.name, "dim": "2:3", "size": "Small", "count": "1"},
        "size_px_map": {"Small":512,"Medium":768,"Large":1024}
    }





def custom_dimension(request):

    dimensions_qs = GenerateDimension.objects.all().order_by("id")
    
    paginator = Paginator(dimensions_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        "dimensions": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_dimension.html", context)


def add_dimension(request):
    if request.method == "POST":
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not label or not value:
            messages.error(request, "กรุณากรอก Label และ Value ให้ครบ")
            return redirect("custom_dimension")

        GenerateDimension.objects.create(label=label, value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Dimension '{label}' ({value}) สำเร็จแล้ว")
    return redirect("custom_dimension")


def edit_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    if request.method == "POST":
        dim.label = request.POST.get("label")
        dim.value = request.POST.get("value")
        dim.is_active = request.POST.get("is_active") == "true"
        dim.save()
        messages.success(request, f"แก้ไข Dimension '{dim.label}' สำเร็จแล้ว")
        return redirect("custom_dimension")
    return render(request, "edit_dimension.html", {"dimension": dim})


def delete_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.delete()
    messages.success(request, f"ลบ Dimension '{dim.label}' สำเร็จแล้ว")
    return redirect("custom_dimension")


def toggle_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.is_active = not dim.is_active
    dim.save()
    state = "Active" if dim.is_active else "Suspended"
    messages.success(request, f"Dimension '{dim.label}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_dimension")


def custom_count(request):

    counts_qs = GenerateCount.objects.all().order_by("id")
    
    paginator = Paginator(counts_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        "counts": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_count.html", context)

def add_count(request):
    if request.method == "POST":
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not value:
            messages.error(request, "กรุณากรอก Value")
            return redirect("custom_count")

        GenerateCount.objects.create(value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Count '{value}' สำเร็จแล้ว")
    return redirect("custom_count")

def edit_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    if request.method == "POST":
        count.value = request.POST.get("value")
        count.is_active = request.POST.get("is_active") == "true"
        count.save()
        messages.success(request, f"แก้ไข Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def delete_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.delete()
    messages.success(request, f"ลบ Count '{count.value}' สำเร็จแล้ว")
    return redirect("custom_count")

def toggle_count(request, pk):
    count = get_object_or_404(GenerateCount, pk=pk)
    count.is_active = not count.is_active
    count.save()
    state = "Active" if count.is_active else "Suspended"
    messages.success(request, f"Count '{count.value}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_count")



def _extract_json_from_text(text):

    json_str = ""
    # 1. Try markdown code block (json optional)
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 2. Fallback: Find the *last* valid outer JSON block
        matches = re.findall(r'(\{.*?\})', text, re.DOTALL)
        if matches:
            # Prefer the last one as it's likely the final answer
            candidate = matches[-1]
            if '"subject"' in candidate:
                json_str = candidate
            else:
                # If last one is small, maybe it's the 1st one? Fallback range
                start_idx = text.find('{')
                end_idx = text.rfind('}') + 1
                if start_idx != -1 and end_idx != -1:
                    json_str = text[start_idx:end_idx]
        else:
             # Last resort
             start_idx = text.find('{')
             end_idx = text.rfind('}') + 1
             if start_idx != -1 and end_idx != -1:
                json_str = text[start_idx:end_idx]
    return json_str

def call_agent_assist(topic, style="", intended_subject=""):
    try:
        template = f"""
You are a creative AI assistant for image generation prompts.

User's Input: "{topic}"
User's Intended StyleTASK:
1. Analyze the "User's Input" (which can be in Thai or English).
2. Generate creative suggestions for each category to help build a detailed image prompt.
3. **OUTPUT MUST BE A VALID JSON OBJECT.**
4. **LANGUAGE RULE: Suggestions must match the language of the User's Input.** 
   - If Input is English -> Suggestions must be in English.
   - If Input is Thai -> Suggestions must be in Thai.

CRITICAL RULES:
- Keys must be English (e.g., "subject", "suggestions").
- Strings must use DOUBLE QUOTES (").
- **EXTRACTION RULE**: The "current" value must be COPIED EXACTLY from the Input. DO NOT TRANSLATE IT.
  - If Input says "Cat", "current" must be "Cat" (NOT "แมว").
  - If Input says "แมว", "current" must be "แมว".
- No extra text.

*** EXAMPLES ***

Example 1 (English Input -> English Output):
Input: "Cat"
Output:
{{
  "subject": {{ "current": "Cat", "suggestions": ["Cute cat", "Orange tabby", "Kitten", "Persian cat"] }},
  "action_pose": {{ "current": "", "suggestions": ["Sleeping", "Jumping", "Sitting by window", "Walking in garden"] }},
  "attributes": {{ "current": "", "suggestions": ["Fluffy fur", "Blue eyes", "Wearing collar", "Long tail"] }},
  "environment_setting": {{ "current": "", "suggestions": ["On a sofa", "In a living room", "On the roof", "In a cardboard box"] }},
  "composition_framing": {{ "current": "", "suggestions": ["Close-up shot", "Low angle", "Bokeh background", "Natural light"] }},
  "style": {{ "current": "", "suggestions": ["Photorealistic", "Watercolor painting", "Cartoon style", "3D Render"] }},
  "lighting": {{ "current": "", "suggestions": ["Morning sunlight", "Soft light", "Studio lighting", "Dark shadows"] }},
  "camera": {{ "current": "", "suggestions": ["Macro lens", "Wide angle", "Eye level", "High angle"] }},
  "mood": {{ "current": "", "suggestions": ["Cute and cheerful", "Warm", "Peaceful", "Playful"] }},
  "negative_prompt": {{ "current": "", "suggestions": ["Blurry image", "Cat with 5 legs", "Too dark", "Watermark"] }}
}}

Example 2 (Thai Input -> Thai Output):
Input: "หญิงสาว"
Output:
{{
  "subject": {{ "current": "หญิงสาว", "suggestions": ["สาวสวย", "ผู้หญิงวัยรุ่น", "นางแบบ", "สาวผมยาว"] }},
  "action_pose": {{ "current": "", "suggestions": ["ยืนยิ้ม", "เดินเล่น", "นั่งอ่านหนังสือ", "ถือดอกไม้"] }},
  "attributes": {{ "current": "", "suggestions": ["ผมสีทอง", "ตาสีฟ้า", "ใส่ชุดเดรส", "ผิวขาว"] }},
  "environment_setting": {{ "current": "", "suggestions": ["ในสวนดอกไม้", "ริมทะเล", "ในคาเฟ่", "บนถนนในเมือง"] }},
  "composition_framing": {{ "current": "", "suggestions": ["ภาพครึ่งตัว", "ภาพเต็มตัว", "หน้าชัดหลังเบลอ", "มุมสูง"] }},
  "style": {{ "current": "", "suggestions": ["ภาพถ่ายสมจริง", "ภาพวาดสีน้ำมัน", "สไตล์อนิเมะ", "ภาพแนวแฟนตาซี"] }},
  "lighting": {{ "current": "", "suggestions": ["แสงแดดยามเช้า", "แสงนวลตา", "แสงไฟสตูดิโอ", "เงามืด"] }},
  "camera": {{ "current": "", "suggestions": ["เลนส์มาโคร", "มุมกว้าง", "ระดับสายตา", "มุมสูง"] }},
  "mood": {{ "current": "", "suggestions": ["น่ารักสดใส", "อบอุ่น", "สงบ", "ขี้เล่น"] }},
  "negative_prompt": {{ "current": "", "suggestions": ["ภาพเบลอ", "แมวมี 5 ขา", "ภาพมืดเกินไป", "ลายน้ำ"] }}
}}

Output the JSON result for the following Input:
Input: "{topic}" (Style: "{style}", Subject: "{intended_subject}")
"""
        result = subprocess.run(
            ["ollama", "run", "llama3.1", template],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300
        )

        output = result.stdout.strip()
        print("[Agent Assist raw output]:\n", output)
        
        json_str = _extract_json_from_text(output)

        # --- Self-Correction / Verification Loop ---
        if json_str:
            print("[Agent Assist]: verifying prompt...")
            verify_template = f"""
You are a Quality Assurance AI.
User Input: "{topic}"
Context: Style="{style}", Subject="{intended_subject}"

Generated JSON:
{json_str}

Check if the Generated JSON accurately reflects the User Input.
1. If it is GOOD and accurate, respond ONLY with the word: "USE"
2. If it is BAD or inaccurate, generate a NEW, CORRECTED JSON object.
"""
            try:
                verify_res = subprocess.run(
                    ["ollama", "run", "llama3.1", verify_template],
                    capture_output=True, text=True, encoding="utf-8", timeout=300
                )
                verify_out = verify_res.stdout.strip()
                print("[Agent Verification Output]:\n", verify_out)
                
                # If response contains a JSON-like block, assume it's a correction
                if "{" in verify_out and "}" in verify_out:
                     corrected_json = _extract_json_from_text(verify_out)
                     if corrected_json:
                         print("[Agent Assist]: Using corrected JSON from verification.")
                         json_str = corrected_json
                elif "USE" in verify_out.upper():
                     print("[Agent Assist]: Prompt approved by verification.")
                else:
                     print("[Agent Assist]: Verification output ambiguous, keeping original.")
            except Exception as ve:
                print(f"[Agent Assist]: Verification failed: {ve}")
        # -------------------------------------------
        
        if json_str:
            try:
                data = json.loads(json_str)
                return data
            except json.JSONDecodeError as e:
                print(f"JSON Parse Error: {e}")
                # Log the extraction for debugging
                print(f"Extracted String: {json_str[:100]}...{json_str[-100:]}")
                return None
        else:
             print("No JSON structure found in output.")
             return None

    except Exception as e:
        print("Agent Assist Error:", e)
        return None

@login_required(login_url='login')
@require_POST
def call_agent_assist_view(request):
    topic = request.POST.get("topic", "").strip()
    style = request.POST.get("style", "").strip()
    intended_subject = request.POST.get("intended_subject", "").strip()
    
    data = call_agent_assist(topic, style, intended_subject)
    
    if data:
        return JsonResponse({
            "status": "success",
            "data": data
        })
    else:
        return JsonResponse({
            "status": "error",
            "message": "AI could not generate suggestions."
        })

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

@staff_required
def custom_model(request):

    models_qs = GenerateModel.objects.all().order_by("id")
    
    paginator = Paginator(models_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, "custom_model.html", {
        "models_data": page_obj,
        "page_obj": page_obj,
    })

@staff_required
def delete_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)  # ใช้ GenerateModel
    model_name = model.name                         # เก็บชื่อไว้ก่อนลบ
    model.delete()

    # ใช้ message framework เพื่อแสดงชื่อที่ถูกลบ

    messages.success(request, f"ลบโมเดล '{model_name}' สำเร็จแล้ว")

    return redirect("custom_model")


@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        models_available = request.POST.get("models_available")
        dimensions = request.POST.get("dimensions")
        sizes = request.POST.get("sizes")
        number_of_images = request.POST.get("number_of_images")

        GenerateSetting.objects.create(
            name=name,
            models_available=models_available,
            dimensions=dimensions,
            sizes=sizes,
            number_of_images=number_of_images,
        )
        return redirect("custom_model")

    return redirect("custom_model")

def edit_model(request, pk):
    model = get_object_or_404(GenerateModel, pk=pk)
    if request.method == "POST":
        model.name = request.POST.get("name")
        model.value = request.POST.get("value")
        model.is_active = request.POST.get("is_active") == "true"
        model.save()
        messages.success(request, f"แก้ไข Model '{model.name}' สำเร็จแล้ว")
    return redirect("custom_model")


def toggle_status(request, pk):
    model = GenerateModel.objects.get(pk=pk)
    model.is_active = not model.is_active   # ใช้ฟิลด์ is_active แทน status
    model.save()
    return redirect("custom_model")

@staff_required
def add_model(request):
    if request.method == "POST":
        name = request.POST.get("name")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not name or not value:
            messages.error(request, "กรุณากรอกทั้ง Name และ Value")
            return redirect("custom_model")

        GenerateModel.objects.create(
            name=name,
            value=value,
            is_active=is_active
        )
        return redirect("custom_model")




# helper
def _get_presets():
    setting = GenerateSetting.objects.first()
    if not setting:
        return {
            "models_available": [{"label": "Nova XL v9.0", "value": "novaOrangeXL_v90.safetensors"}],
            "dimensions": ["2:3", "1:1", "16:9"],
            "sizes": ["Small", "Medium", "Large"],
            "numbers": ["1", "2", "3", "4"],
            "defaults": {"model":"novaOrangeXL_v90.safetensors","dim":"2:3","size":"Small","count":"1"},
            "size_px_map": {"Small":512,"Medium":768,"Large":1024},
        }
    return {
        "models_available": [m.strip() for m in setting.models_available.split(",")],
        "dimensions": [d.strip() for d in setting.dimensions.split(",")],
        "sizes": [s.strip() for s in setting.sizes.split(",")],
        "numbers": [n.strip() for n in setting.number_of_images.split(",")],
        "defaults": {"model": setting.name, "dim": "2:3", "size": "Small", "count": "1"},
        "size_px_map": {"Small":512,"Medium":768,"Large":1024}
    }





def custom_dimension(request):

    dimensions_qs = GenerateDimension.objects.all().order_by("id")
    
    paginator = Paginator(dimensions_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        "dimensions": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_dimension.html", context)


def add_dimension(request):
    if request.method == "POST":
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not label or not value:
            messages.error(request, "กรุณากรอก Label และ Value ให้ครบ")
            return redirect("custom_dimension")

        GenerateDimension.objects.create(label=label, value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Dimension '{label}' ({value}) สำเร็จแล้ว")
    return redirect("custom_dimension")


def edit_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    if request.method == "POST":
        dim.label = request.POST.get("label")
        dim.value = request.POST.get("value")
        dim.is_active = request.POST.get("is_active") == "true"
        dim.save()
        messages.success(request, f"แก้ไข Dimension '{dim.label}' สำเร็จแล้ว")
        return redirect("custom_dimension")
    return render(request, "edit_dimension.html", {"dimension": dim})


def delete_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.delete()
    messages.success(request, f"ลบ Dimension '{dim.label}' สำเร็จแล้ว")
    return redirect("custom_dimension")


def toggle_dimension(request, pk):
    dim = get_object_or_404(GenerateDimension, pk=pk)
    dim.is_active = not dim.is_active
    dim.save()
    state = "Active" if dim.is_active else "Suspended"
    messages.success(request, f"Dimension '{dim.label}' ถูกเปลี่ยนเป็น {state}")
    return redirect("custom_dimension")


def custom_count(request):

    counts_qs = GenerateCount.objects.all().order_by("id")
    
    paginator = Paginator(counts_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        "counts": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "custom_count.html", context)

def add_count(request):
    if request.method == "POST":
        value = request.POST.get("value")
        is_active = request.POST.get("is_active") == "true"

        if not value:
            messages.error(request, "กรุณากรอก Value")
            return redirect("custom_count")

        GenerateCount.objects.create(value=value, is_active=is_active)
        messages.success(request, f"เพิ่ม Count '{value}' สำเร็จแล้ว")
    return redirect("custom_count")





@admin_required
def dashboard_view(request):
    """
    Admin Dashboard: Overview of system statistics.
    Legacy version with detailed metrics.
    """

    today = timezone.now().date()
    
    # Basic Counters
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    total_comments = Comment.objects.count()
    total_generated_images = GenerateHistory.objects.count()

    # Activity Monitoring
    active_users_today = User.objects.filter(last_login__date=today).count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    generated_today = GenerateHistory.objects.filter(created_at__date=today).count()
    active_models = GenerateModel.objects.filter(is_active=True).count()
    tags_count = Tag.objects.count()

    # Recent Data
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_images = GenerateHistory.objects.select_related('user').order_by('-created_at')[:5]

    # Model Usage Stats
    model_usage_data = GenerateHistory.objects.values('model_name').annotate(count=Count('model_name')).order_by('-count')[:5]
    # Calculate percentages
    model_usage = []
    if total_generated_images > 0:
        for m in model_usage_data:
            percent = (m['count'] / total_generated_images) * 100
            model_usage.append({
                'model_name': m['model_name'],
                'count': m['count'],
                'percent': round(percent, 1)
            })

    # Tag Usage Stats
    tag_usage = Tag.objects.annotate(count=Count('posts')).order_by('-count')[:5]

    context = {
        "total_users": total_users,
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_generated_images": total_generated_images,
        "active_users_today": active_users_today,
        "new_users_today": new_users_today,
        "generated_today": generated_today,
        "active_models": active_models,
        "tags_count": tags_count,
        "recent_users": recent_users,
        "recent_images": recent_images,
        "model_usage": model_usage,
        "tag_usage": tag_usage,
    }
    return render(request, "dashboard.html", context)

# ==========================================
# 3.6 จัดการเนื้อหา (Content Management)
# ==========================================

@admin_required
def admin_post_list(request):
    posts = Post.objects.select_related('user').order_by('-created_at')
    rows = []
    for p in posts:
        # Create row data
        image_html = f'<img src="{p.history.image_url}" class="w-10 h-10 object-cover rounded">' if p.history and p.history.image_url else "-"
        rows.append({
            'id': p.id,
            'data': [
                image_html,
                p.title or "(No Title)",
                p.user.username,
                p.created_at.strftime("%Y-%m-%d %H:%M")
            ]
        })
    
    return render(request, "admin_data_list.html", {
        "title": "Manage Posts",
        "headers": ["Image", "Title", "Owner", "Created At"],
        "rows": rows,
        "delete_url_name": "admin_delete_post"
    })

@admin_required
@require_POST
def admin_delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.delete()
    messages.success(request, "Post deleted successfully.")
    return redirect('admin_post_list')

@admin_required
def admin_comment_list(request):
    comments = Comment.objects.select_related('user', 'post').order_by('-created_at')
    rows = []
    for c in comments:
        rows.append({
            'id': c.id,
            'data': [
                c.text[:50] + "..." if len(c.text) > 50 else c.text,
                c.user.username,
                f"Post #{c.post.id}",
                c.created_at.strftime("%Y-%m-%d %H:%M")
            ]
        })
    
    return render(request, "admin_data_list.html", {
        "title": "Manage Comments",
        "headers": ["Comment", "User", "Post", "Date"],
        "rows": rows,
        "delete_url_name": "admin_delete_comment"
    })

@admin_required
@require_POST
def admin_delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    comment.delete()
    messages.success(request, "Comment deleted successfully.")
    return redirect('admin_comment_list')

@admin_required
def admin_image_list(request):

    filter_type = request.GET.get('filter')
    today = timezone.now().date()
    
    if filter_type == 'today':
        images = GenerateHistory.objects.filter(created_at__date=today).select_related('user').order_by('-created_at')
        title = f"ภาพที่สร้างวันนี้ (Today: {today})"
    else:
        images = GenerateHistory.objects.select_related('user').order_by('-created_at')
        title = "จัดการรูปภาพที่สร้าง (All Generated Images)"
    rows = []
    for img in images:
        image_html = f'<img src="{img.image_url}" class="w-10 h-10 object-cover rounded">'
        rows.append({
            'id': img.id,
            'data': [
                image_html,
                img.positive_prompt[:50] + "...",
                img.user.username,
                img.model_name
            ]
        })
    
    return render(request, "admin_data_list.html", {
        "title": title,
        "headers": ["Image", "Prompt", "User", "Model"],
        "rows": rows,
        "delete_url_name": "admin_delete_image"
    })

@admin_required
@require_POST
def admin_delete_image(request, pk):
    img = get_object_or_404(GenerateHistory, pk=pk)
    img.delete()
    messages.success(request, "Image history deleted successfully.")
    return redirect('admin_image_list')

@admin_required
def admin_tag_list(request):

    
    sort_param = request.GET.get('sort')
    tags_qs = Tag.objects.annotate(usage_count=Count('posts'))
    
    if sort_param == 'usage_asc':
        tags_qs = tags_qs.order_by('usage_count')
    elif sort_param == 'usage_desc':
        tags_qs = tags_qs.order_by('-usage_count')
    else:
        tags_qs = tags_qs.order_by('category', 'name')
        
    paginator = Paginator(tags_qs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        "tags": page_obj,
        "page_obj": page_obj,
        "current_sort": sort_param
    }
    return render(request, "admin_tag_list.html", context)

@admin_required
@require_POST
def admin_add_tag(request):
    name = request.POST.get("name")
    category = request.POST.get("category", "Uncategorized")
    
    if name:
        name = name[:100]
        category = category[:100]
        Tag.objects.create(name=name, category=category)
        messages.success(request, f"เพิ่ม Tag '{name}' สำเร็จแล้ว")
    else:
        messages.error(request, "กรุณาระบุชื่อ Tag")
        
    return redirect("admin_tag_list")

@admin_required
@require_POST
def admin_edit_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    name = request.POST.get("name")
    category = request.POST.get("category", "Uncategorized")
    
    if name:
        tag.name = name[:100]
        tag.category = category[:100]
        tag.save()
        messages.success(request, f"แก้ไข Tag '{name}' สำเร็จแล้ว")
    else:
        messages.error(request, "กรุณาระบุชื่อ Tag")
        
    return redirect("admin_tag_list")

@admin_required
@require_POST
def admin_delete_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    tag.delete()
    messages.success(request, "Tag deleted successfully.")
    return redirect('admin_tag_list')





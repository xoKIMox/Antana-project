from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

def user_directory_path(instance, filename):
    return f'user_{instance.user.id}/{filename}'

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_image = models.ImageField(upload_to=user_directory_path, default='default.jpg')

    def __str__(self):
        return self.user.username

class GenerateHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=255)
    positive_prompt = models.TextField()
    negative_prompt = models.TextField(null=True, blank=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    image_file = models.ImageField(upload_to='generated_images/%Y/%m/%d/', blank=True, null=True)
    seed = models.BigIntegerField()

    # ให้ดาว 1–5, อนุญาตให้เว้นว่างได้ (ยังไม่กดดาว)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="คะแนน 1-5 ดาว"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} | {self.model_name} | {self.positive_prompt[:30]}"
    
class Tag(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, default="Uncategorized")  # ✅ เพิ่ม default ตรงนี้

    def __str__(self):
        return f"{self.name} ({self.category})"


class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    history = models.ForeignKey(GenerateHistory, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, blank=True)
    caption = models.TextField()
    model_used = models.CharField(max_length=255, blank=True)
    tags = models.ManyToManyField(Tag, related_name='posts', blank=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # String representation for admin

    def __str__(self):
        return self.title or f"{self.user.username} - {self.caption[:30]}"
    
class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username}: {self.text[:30]}"

class GenerateSetting(models.Model):
    name = models.CharField(max_length=100, default="Default")

    default_model = models.ForeignKey("GenerateModel", on_delete=models.SET_NULL, null=True, blank=True)
    default_dimension = models.ForeignKey("GenerateDimension", on_delete=models.SET_NULL, null=True, blank=True)
    default_size = models.ForeignKey("GenerateSize", on_delete=models.SET_NULL, null=True, blank=True)
    default_count = models.ForeignKey("GenerateCount", on_delete=models.SET_NULL, null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SidebarMenu(models.Model):
    name = models.CharField(max_length=100)      # ชื่อเมนู เช่น "โพสต์"
    url = models.CharField(max_length=200)       # ลิงก์ เช่น "/posts/" หรือชื่อ urlpattern
    order = models.PositiveIntegerField(default=0)  # ใช้จัดลำดับเมนู

    class Meta:
        ordering = ['order']   # เรียงตาม order อัตโนมัติ

    def __str__(self):
        return self.name


# เก็บรายชื่อโมเดล
class GenerateModel(models.Model):
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# เก็บขนาดภาพ
class GenerateSize(models.Model):
    label = models.CharField(max_length=50)   # เช่น Small, Medium, Large
    px = models.IntegerField(default=512)     # เช่น 512, 768, 1024
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.label} ({self.px}px)"


# เก็บจำนวนภาพที่เลือกได้
class GenerateCount(models.Model):
    value = models.PositiveIntegerField(default=1)  # เช่น 1, 2, 3, 4
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.value} {'(Active)' if self.is_active else '(Suspended)'}"

class GenerateDimension(models.Model):
    label = models.CharField(max_length=50)
    value = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.label} ({self.value})"




    

    

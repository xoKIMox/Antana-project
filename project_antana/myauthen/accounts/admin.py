# myauthen/accounts/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.db.models import Count
from django.http import HttpResponse
import csv
from .models import GenerateModel, GenerateDimension, GenerateSize, GenerateCount

from .models import GenerateSetting, GenerateHistory, Post, SidebarMenu, Tag, Comment
# ถ้ามี Profile model และอยากจัดการในแอดมินด้วย ปลดคอมเมนต์บรรทัดนี้
# from .models import Profile


# ---------------------------
# Helpers
# ---------------------------
def short(text, limit=80):
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"

def _csv_response(filename, header_row, rows_iter):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(resp)
    writer.writerow(header_row)
    for row in rows_iter:
        writer.writerow(row)
    return resp


# ---------------------------
# GenerateSetting
# ---------------------------
@admin.register(GenerateModel)
class GenerateModelAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "is_active")
    search_fields = ("name", "value")

@admin.register(GenerateSize)
class GenerateSizeAdmin(admin.ModelAdmin):
    list_display = ("label", "px", "is_active")

@admin.register(GenerateCount)
class GenerateCountAdmin(admin.ModelAdmin):
    list_display = ("value", "is_active")


# ---------------------------
# GenerateHistory
# ---------------------------
@admin.action(description="Export selected GenerateHistory to CSV")
def export_histories_csv(modeladmin, request, queryset):
    header = ["id", "user", "model_name", "seed", "image_url", "rating", "created_at", "positive_prompt", "negative_prompt"]
    def iter_rows():
        for h in queryset.select_related("user"):
            yield [
                h.id,
                getattr(h.user, "username", ""),
                h.model_name,
                h.seed,
                h.image_url,
                h.rating,
                h.created_at,
                h.positive_prompt,
                h.negative_prompt,
            ]
    return _csv_response("generate_histories.csv", header, iter_rows())

@admin.register(GenerateHistory)
class GenerateHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user_link", "model_name", "seed", "rating", "created_at",
        "thumb", "positive_short",
    )
    list_filter = ("model_name", "rating", "created_at")
    search_fields = ("positive_prompt", "negative_prompt", "user__username", "model_name", "seed")
    readonly_fields = ("thumb", "created_at")
    date_hierarchy = "created_at"
    actions = [export_histories_csv]
    ordering = ("-created_at",)

    fieldsets = (
        (None, {
            "fields": ("user", "model_name", "seed", "rating")
        }),
        ("Prompts", {
            "fields": ("positive_prompt", "negative_prompt")
        }),
        ("Result", {
            "fields": ("image_url", "thumb", "created_at")
        }),
    )

    def user_link(self, obj):
        if obj.user_id:
            url = reverse("admin:auth_user_change", args=[obj.user_id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"
    user_link.short_description = "User"

    def positive_short(self, obj):
        return short(obj.positive_prompt, 60)
    positive_short.short_description = "Prompt+"

    def thumb(self, obj):
        if not obj.image_url:
            return "-"
        # แสดงรูปจาก URL
        return format_html('<img src="{}" style="height:64px;width:auto;border-radius:6px;object-fit:cover;" />', obj.image_url)
    thumb.short_description = "Preview"


# ---------------------------
# Post
# ---------------------------
class TagInline(admin.TabularInline):
    model = Post.tags.through
    extra = 0
    verbose_name = "Tag"
    verbose_name_plural = "Tags"

@admin.action(description="Export selected Posts to CSV")
def export_posts_csv(modeladmin, request, queryset):
    header = ["id", "user", "title", "caption", "model_used", "created_at", "history_id", "history_image_url", "tags"]
    def iter_rows():
        qs = queryset.select_related("user", "history").prefetch_related("tags")
        for p in qs:
            yield [
                p.id,
                getattr(p.user, "username", ""),
                p.title,
                p.caption,
                p.model_used,
                getattr(p, "created_at", ""),
                getattr(p.history, "id", ""),
                getattr(p.history, "image_url", ""),
                ", ".join([t.name for t in p.tags.all()]),
            ]
    return _csv_response("posts.csv", header, iter_rows())

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title_short", "user_link", "model_used", "created_at", "history_preview")
    search_fields = ("title", "caption", "user__username", "model_used", "history__positive_prompt")
    list_filter = ("model_used", "created_at", "tags")
    date_hierarchy = "created_at"
    inlines = [TagInline]
    actions = [export_posts_csv]
    ordering = ("-created_at",)

    fieldsets = (
        (None, {
            "fields": ("user", "title", "caption", "model_used")
        }),
        ("History", {
            "description": "โพสต์นี้โยงกับผลการ Generate ภาพ",
            "fields": ("history", "history_preview")
        }),
        ("Tags", {
            "fields": ("tags",),
        }),
    )
    readonly_fields = ("history_preview",)

    def title_short(self, obj):
        return short(obj.title, 40) or "(no title)"
    title_short.short_description = "Title"

    def user_link(self, obj):
        if obj.user_id:
            url = reverse("admin:auth_user_change", args=[obj.user_id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"
    user_link.short_description = "User"

    def history_preview(self, obj):
        if obj.history and obj.history.image_url:
            url = obj.history.image_url
            return format_html('<a href="{}" target="_blank"><img src="{}" style="height:80px;border-radius:6px;" /></a>', url, url)
        return "-"


# ---------------------------
# Tag
# ---------------------------
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "posts_count")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_posts_count=Count("post"))

    def posts_count(self, obj):
        return getattr(obj, "_posts_count", 0)
    posts_count.short_description = "Posts"


# ---------------------------
# Comment
# ---------------------------
@admin.action(description="Delete selected comments (soft advice: confirm!)")
def delete_comments(modeladmin, request, queryset):
    # คุณสามารถเปลี่ยนเป็น soft-delete ได้ถ้ามีฟิลด์สถานะ
    queryset.delete()

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post_link", "user_link", "text_short", "created_at")
    search_fields = ("text", "user__username", "post__title", "post__caption")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    actions = [delete_comments]
    ordering = ("-created_at",)

    def text_short(self, obj):
        return short(obj.text, 60)
    text_short.short_description = "Comment"

    def post_link(self, obj):
        if obj.post_id:
            url = reverse("admin:accounts_post_change", args=[obj.post_id])
            return format_html('<a href="{}">Post #{}</a>', url, obj.post_id)
        return "-"
    post_link.short_description = "Post"

    def user_link(self, obj):
        if obj.user_id:
            url = reverse("admin:auth_user_change", args=[obj.user_id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"
    user_link.short_description = "User"


# ---------------------------
# (ถ้ามี) Profile
# ---------------------------
# @admin.register(Profile)
# class ProfileAdmin(admin.ModelAdmin):
#     list_display = ("id", "user", "profile_image")
#     search_fields = ("user__username",)


# ---------------------------
# Admin site branding (optional)
# ---------------------------
admin.site.site_header = "Artana Admin"
admin.site.site_title = "Artana Admin"
admin.site.index_title = "Administration"


@admin.register(SidebarMenu)
class SidebarMenuAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'order')
    ordering = ('order',)

@admin.register(GenerateDimension)
class GenerateDimensionAdmin(admin.ModelAdmin):
    list_display = ("label", "value", "is_active")



from . import views
from django.urls import path


urlpatterns = [
    # ==============================
    # Authentication & Account
    # ==============================
    path('', views.welcome_page, name='login_register'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password_view, name='change_password'),
    path("settings/", views.settings_view, name="settings"),
    path("settings/delete/", views.delete_account_confirm, name="delete_account_confirm"),

    # ==============================
    # Profile
    # ==============================
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile_view, name='edit_profile'),
    path('user/<str:username>/', views.user_profile, name='user_profile'),

    # ==============================
    # Feed & Posts
    # ==============================
    path('home/', views.post_feed_view, name='home'),
    path('post_feed/', views.post_feed_view, name='post_feed'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    path('post/<int:post_id>/toggle-like/', views.toggle_like, name='toggle_like'),
    
    # ==============================
    # Comments
    # ==============================
    path('post/<int:post_id>/add-comment/', views.add_comment, name='add_comment'),
    path('post/<int:post_id>/comment-modal/', views.comment_modal, name='comment_modal'),
    path('comment/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),

    # ==============================
    # Image Generation & AI
    # ==============================
    # Note: 'generate' and 'generate_view' point to the same view, commonly used
    path('generate/', views.generate_view, name='generate'),
    path("generate/", views.generate_view, name="generate_view"), 
    path('generate/delete-history/<int:pk>/', views.delete_history_view, name='delete_history_view'),
    path("generate/preview-frame/", views.generate_preview_frame, name="generate_preview_frame"),
    path("generate/ai-prompt/", views.call_agent_view, name="call_agent"),
    path("generate/translate-prompt/", views.translate_prompt_view, name="translate_prompt"),
    path("generate/ai-assist/", views.call_agent_assist_view, name="call_agent_assist"),
    path("generate/share-post/<int:history_id>/", views.share_post, name="share_post"),
    path("generate/share/<int:history_id>/", views.share_post, name="share_post"), # Duplicate pattern check if needed

    # ==============================
    # Search & Tags
    # ==============================
    path("ajax/search/", views.ajax_search_posts, name="ajax_search_posts"),
    path('test_tags/', views.test_extract_tags, name='test_tags'),

    # ==============================
    # Custom Database Models (Dimensions, Counts)
    # ==============================
    # Custom Model
    path("custom_model/", views.custom_model, name="custom_model"),
    path("custom_model/add/", views.add_model, name="add_model"),
    path("edit-model/<int:pk>/", views.edit_model, name="edit_model"),
    path("custom_model/delete/<int:pk>/", views.delete_model, name="delete_model"),
    path("custom_model/toggle/<int:pk>/", views.toggle_status, name="toggle_status"),

    # Dimension
    path("custom-dimension/", views.custom_dimension, name="custom_dimension"),
    path("add-dimension/", views.add_dimension, name="add_dimension"),
    path("edit-dimension/<int:pk>/", views.edit_dimension, name="edit_dimension"),
    path("delete-dimension/<int:pk>/", views.delete_dimension, name="delete_dimension"),
    path("toggle-dimension/<int:pk>/", views.toggle_dimension, name="toggle_dimension"),

    # Count
    path("custom-count/", views.custom_count, name="custom_count"),
    path("add-count/", views.add_count, name="add_count"),
    path("edit-count/<int:pk>/", views.edit_count, name="edit_count"),
    path("delete-count/<int:pk>/", views.delete_count, name="delete_count"),
    path("toggle-count/<int:pk>/", views.toggle_count, name="toggle_count"),

    # ==============================
    # Admin & Dashboard
    # ==============================
    path("custom_admin/", views.custom_admin, name="custom_admin"),
    path("dashboard/", views.dashboard_view, name="admin_dashboard"),

    # User Management
    path("custom_admin/user/add/", views.admin_add_user, name="admin_add_user"), 
    path("custom_admin/user/<int:user_id>/toggle-active/", views.admin_toggle_user_active, name="admin_toggle_user_active"),
    path("custom_admin/user/<int:user_id>/toggle-staff/", views.admin_toggle_user_staff, name="admin_toggle_user_staff"),
    path("custom_admin/user/<int:user_id>/delete/", views.admin_delete_user, name="admin_delete_user"),

    # Admin Content Management
    path("dashboard/posts/", views.admin_post_list, name="admin_post_list"),
    path("dashboard/posts/delete/<int:pk>/", views.admin_delete_post, name="admin_delete_post"),
    
    path("dashboard/comments/", views.admin_comment_list, name="admin_comment_list"),
    path("dashboard/comments/delete/<int:pk>/", views.admin_delete_comment, name="admin_delete_comment"),
    
    path("dashboard/images/", views.admin_image_list, name="admin_image_list"),
    path("dashboard/images/delete/<int:pk>/", views.admin_delete_image, name="admin_delete_image"),
    
    path("dashboard/tags/", views.admin_tag_list, name="admin_tag_list"),
    path("dashboard/tags/add/", views.admin_add_tag, name="admin_add_tag"),
    path("dashboard/tags/edit/<int:pk>/", views.admin_edit_tag, name="admin_edit_tag"),
    path("dashboard/tags/delete/<int:pk>/", views.admin_delete_tag, name="admin_delete_tag"),
    
    path("dashboard/ajax/widget/", views.ajax_dashboard_widget, name="ajax_dashboard_widget"),
]
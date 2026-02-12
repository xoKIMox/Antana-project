@staff_required
def dashboard_view(request):
    """
    Admin Dashboard: Overview of system statistics.
    """
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    total_comments = Comment.objects.count()
    total_images = GenerateHistory.objects.count()
    
    # Recent activity (optional)
    recent_posts = Post.objects.order_by('-created_at')[:5]
    recent_users = User.objects.order_by('-date_joined')[:5]

    context = {
        "total_users": total_users,
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_images": total_images,
        "recent_posts": recent_posts,
        "recent_users": recent_users,
    }
    return render(request, "dashboard.html", context)

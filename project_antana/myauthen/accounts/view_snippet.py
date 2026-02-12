
@login_required(login_url='login')
@require_POST
def delete_history_view(request, pk):
    history = get_object_or_404(GenerateHistory, pk=pk)
    # Optional: check ownership
    if history.user != request.user:
        return JsonResponse({"status": "error", "message": "Ownership denied"}, status=403)
        
    history.delete()
    return JsonResponse({"status": "success"})

from django import forms
from .models import Post, Tag ,Comment

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'caption',]
        
class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'แสดงความคิดเห็น...'})
        }
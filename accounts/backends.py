from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailBackend(ModelBackend):
    """مصادقة المستخدم باستخدام البريد الإلكتروني بدلاً من اسم المستخدم"""
    
    def authenticate(self, request, email=None, password=None, **kwargs):
        UserModel = get_user_model()
        
        if email is None:
            email = kwargs.get(UserModel.USERNAME_FIELD)
        
        if email is None or password is None:
            return None
        
        try:
            user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None

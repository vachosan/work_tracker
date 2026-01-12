from django.contrib.auth.models import Group
from django.contrib import messages
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress


class CustomAccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix, email, context):
        user = context.get("user")
        if user:
            user_label = user.get_username() or getattr(user, "email", "") or "(neznámý uživatel)"
        else:
            user_label = "(neznámý uživatel)"
        context["user_label"] = user_label
        return super().send_mail(template_prefix, email, context)

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=commit)
        if form is not None:
            group, _ = Group.objects.get_or_create(name="must_verify_email")
            user.groups.add(group)
        return user

    def is_open_for_login(self, request, user):
        if not super().is_open_for_login(request, user):
            return False
        must_verify = user.groups.filter(name="must_verify_email").exists()
        if not must_verify:
            return True
        if EmailAddress.objects.filter(user=user, verified=True).exists():
            return True
        messages.error(request, "Před přihlášením potvrďte e-mail.")
        return False

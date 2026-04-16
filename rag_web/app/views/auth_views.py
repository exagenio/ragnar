from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from app.forms import RegisterForm


class UserLoginView(LoginView):
    template_name = "auth/login.html"
    authentication_form = AuthenticationForm
    redirect_authenticated_user = True


def register(request):
    if request.user.is_authenticated:
        return redirect("project_create")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Your account has been created successfully.")
            return redirect("project_create")
    else:
        form = RegisterForm()

    return render(request, "auth/register.html", {"form": form})


login_view = UserLoginView.as_view()

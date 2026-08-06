from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    HeroSlide,
    Order,
    RoleProfile,
    UserProfile,
)
from .order_status import get_valid_next_statuses


User = get_user_model()


class RegistrationForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Full Name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}),
    )
    confirm_password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm Password"}),
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        name = (self.cleaned_data.get("name") or "").strip()
        candidate_user = User(username=email or name or "user", email=email)
        validate_password(password, user=candidate_user)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password") or ""
        confirm_password = cleaned_data.get("confirm_password") or ""

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data

    def save(self):
        from .permissions import ensure_default_roles

        ensure_default_roles()

        name = (self.cleaned_data["name"] or "").strip()
        email = (self.cleaned_data["email"] or "").strip().lower()
        password = self.cleaned_data["password"]
        name_parts = name.split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        user = User(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_staff=False,
        )
        user.set_password(password)
        user.save()

        default_group = Group.objects.filter(name="customers").first()
        if default_group is not None:
            user.groups.add(default_group)

        return user


class EmailAuthenticationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}),
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()


class CheckoutOrderForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    phone = forms.CharField(max_length=50)
    email = forms.EmailField(required=False)
    address = forms.CharField(widget=forms.Textarea)
    district = forms.CharField(max_length=120)
    thana = forms.CharField(max_length=120, required=False)
    postal = forms.CharField(max_length=20, required=False)
    order_notes = forms.CharField(required=False, widget=forms.Textarea)

    def _clean_optional_text(self, field_name):
        return (self.cleaned_data.get(field_name) or "").strip()

    def clean_full_name(self):
        return (self.cleaned_data.get("full_name") or "").strip()

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            raise ValidationError("Phone number is required.")
        return phone

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_address(self):
        address = (self.cleaned_data.get("address") or "").strip()
        if not address:
            raise ValidationError("Full address is required.")
        return address

    def clean_district(self):
        district = (self.cleaned_data.get("district") or "").strip()
        if not district:
            raise ValidationError("District is required.")
        return district

    def clean_thana(self):
        return self._clean_optional_text("thana")

    def clean_postal(self):
        return self._clean_optional_text("postal")

    def clean_order_notes(self):
        return self._clean_optional_text("order_notes")


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=Order.Status.choices,
        initial=Order.Status.PENDING,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Required for cancellation or return",
            }
        ),
    )

    def __init__(self, *args, order=None, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        self.has_available_transitions = False
        if order is not None:
            next_statuses = get_valid_next_statuses(order.status)
            self.has_available_transitions = bool(next_statuses)
            self.fields["status"].choices = [
                (status, dict(Order.Status.choices)[status]) for status in next_statuses
            ]
            if next_statuses and not self.is_bound:
                self.fields["status"].initial = next_statuses[0]

    def clean_status(self):
        status = self.cleaned_data["status"]
        if self.order is not None and status not in get_valid_next_statuses(self.order.status):
            raise ValidationError("This status is not available from the order's current status.")
        return status

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        note = (cleaned_data.get("note") or "").strip()
        if status in {Order.Status.CANCELLED, Order.Status.RETURNED} and not note:
            self.add_error("note", "Please provide a reason for this status change.")
        cleaned_data["note"] = note
        return cleaned_data


class DashboardProfileForm(forms.ModelForm):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Full Name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
    )

    class Meta:
        model = UserProfile
        fields = ["image", "phone", "address"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+8801XXXXXXXXX"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Address"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["name"].initial = user.get_full_name().strip() or user.email or user.username
            self.fields["email"].initial = user.email

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        existing = User.objects.filter(email__iexact=email)
        if self.user is not None:
            existing = existing.exclude(pk=self.user.pk)
        if existing.exists():
            raise ValidationError("An account with this email already exists.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.user is None:
            raise ValidationError("User is required for profile updates.")

        full_name = (self.cleaned_data.get("name") or "").strip()
        email = self.cleaned_data["email"]
        first_name, _, last_name = full_name.partition(" ")
        self.user.first_name = first_name
        self.user.last_name = last_name
        self.user.email = email
        self.user.username = email
        if commit:
            self.user.save(update_fields=["first_name", "last_name", "email", "username"])
            profile.user = self.user
            profile.save()
            self.save_m2m()
        return profile


class DashboardPasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update({"class": "form-control", "placeholder": "Current password"})
        self.fields["new_password1"].widget.attrs.update({"class": "form-control", "placeholder": "New password"})
        self.fields["new_password2"].widget.attrs.update({"class": "form-control", "placeholder": "Confirm new password"})


class RoleForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Manager"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional"}),
    )
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, role=None, **kwargs):
        self.role = role
        super().__init__(*args, **kwargs)

        if role is not None:
            profile, _ = RoleProfile.objects.get_or_create(group=role)
            self.fields["name"].initial = role.name
            self.fields["description"].initial = profile.description
            self.fields["is_active"].initial = profile.is_active
            if profile.is_system:
                self.fields["name"].widget.attrs["readonly"] = True
                self.fields["name"].help_text = "System role names cannot be changed."

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Role name is required.")

        existing = Group.objects.filter(name__iexact=name)
        if self.role is not None:
            existing = existing.exclude(pk=self.role.pk)

        if existing.exists():
            raise ValidationError("A role with this name already exists.")

        if self.role is not None:
            profile, _ = RoleProfile.objects.get_or_create(group=self.role)
            if profile.is_system and name != self.role.name:
                raise ValidationError("System role names cannot be changed.")

        return name

    @transaction.atomic
    def save(self):
        name = self.cleaned_data["name"]
        description = (self.cleaned_data.get("description") or "").strip()
        is_active = self.cleaned_data.get("is_active", False)

        if self.role is None:
            role = Group.objects.create(name=name)
        else:
            role = self.role
            profile, _ = RoleProfile.objects.get_or_create(group=role)
            if not profile.is_system:
                role.name = name
                role.save(update_fields=["name"])

        profile, _ = RoleProfile.objects.get_or_create(group=role)
        profile.description = description
        profile.is_active = is_active
        profile.save(update_fields=["description", "is_active", "updated_at"] if profile.pk else None)
        return role


class HeroSlideForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].help_text = (
            "Enter the full heading once. If you also provide a highlighted phrase below and it exists in the title, "
            "that part will be styled instead of repeated."
        )
        self.fields["title_highlight"].help_text = (
            "Optional. Use a word or phrase from the title to highlight it, or leave blank."
        )
        self.fields["image"].help_text = (
            f"Recommended image size: {HeroSlide.IMAGE_SIZE[0]} x {HeroSlide.IMAGE_SIZE[1]} pixels. "
            "Uploads are automatically cropped and resized to fit this format."
        )

    class Meta:
        model = HeroSlide
        fields = [
            "name",
            "eyebrow",
            "title",
            "title_highlight",
            "description",
            "image",
            "primary_button_label",
            "primary_button_url",
            "secondary_button_label",
            "secondary_button_url",
            "content_alignment",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Slide name for dashboard use"}),
            "eyebrow": forms.TextInput(attrs={"class": "form-control", "placeholder": "Top small label"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Main headline"}),
            "title_highlight": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Highlighted word or phrase"}
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Slide description"}
            ),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "primary_button_label": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Primary button label"}
            ),
            "primary_button_url": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "/products/ or full URL"}
            ),
            "secondary_button_label": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Secondary button label"}
            ),
            "secondary_button_url": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "/blog/ or full URL"}
            ),
            "content_alignment": forms.Select(attrs={"class": "form-select"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }



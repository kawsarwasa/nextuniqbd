from django import forms
from PIL import Image, UnidentifiedImageError

from .models import CompanyProfile


class CompanyProfileForm(forms.ModelForm):
    MAX_LOGO_PIXELS = 2_000_000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logo"].help_text = (
            "Maximum 2 megapixels; for a square source, use 1400 x 1400 px or smaller. "
            "The uploaded logo is converted to 240 x 80 px."
        )

    class Meta:
        model = CompanyProfile
        fields = ["company_name", "logo", "sort_order", "is_active"]
        widgets = {
            "company_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "SBRevo"}
            ),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if not logo:
            return logo

        try:
            image = Image.open(logo)
            image.verify()
        except (UnidentifiedImageError, OSError):
            raise forms.ValidationError("Upload a valid image file.")

        width, height = image.size
        if width * height > self.MAX_LOGO_PIXELS:
            raise forms.ValidationError(
                "Logo image exceeds the 2 megapixel limit. "
                "For a square source, resize to 1400 x 1400 px or smaller."
            )

        logo.seek(0)
        return logo

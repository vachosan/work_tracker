from django.db import transaction

from .models import Dataset

SYSTEM_DATASET_NAME = "Veřejná stromová mapa"


def get_system_dataset() -> Dataset:
    """Returns the singleton system dataset, creating it if needed."""
    with transaction.atomic():
        dataset, _ = Dataset.objects.get_or_create(
            is_system=True,
            defaults={
                "name": SYSTEM_DATASET_NAME,
                "visibility": Dataset.Visibility.PUBLIC,
                "allow_public_observations": True,
            },
        )
    return dataset


def dataset_visible_to_user(dataset: Dataset, user) -> bool:
    """Determines whether the candidate dataset can be seen by the user."""
    if dataset.visibility == Dataset.Visibility.PUBLIC:
        return bool(user and user.is_authenticated)
    return False

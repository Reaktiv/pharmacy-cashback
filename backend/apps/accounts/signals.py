"""Keeps UserProfile in sync with the User/Seller rows it's tied to.

Wired up in AccountsConfig.ready() (Django requires signal receivers to be
imported somewhere for @receiver to register them, and ready() is the
documented place to do that).
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Seller, UserProfile


@receiver(post_save, sender=User)
def create_default_profile(sender, instance, created, **kwargs):
    """Every User needs a UserProfile to exist — code across the app reads
    `request.user.profile` via getattr(..., None) and treats "missing" as
    "no access" rather than prompting setup, so a User created without one
    (e.g. via Django's own "Add user" admin page) silently has no way to
    ever be granted a role. Defaulting to UNASSIGNED costs nothing: it has
    no tenant/branch and matches none of the HasRole permission checks, so
    a fresh account can do nothing until an admin assigns a real role.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Seller)
def sync_profile_with_seller(sender, instance, **kwargs):
    """A Seller row carries the branch/phone/full_name a seller role
    actually needs, which UserProfile.role alone can't supply — so
    provisioning always flows this direction: creating or re-branching a
    Seller is what makes its linked profile a seller, not the reverse.

    full_name/phone are also mirrored onto the profile here (whether the
    Seller was just edited by a branch manager via SellerSerializer, or by
    the seller themselves via MeSerializer.update, which writes to Seller
    first) — keeping both readable from the one place a self-service
    profile page always checks (UserProfile), without making Seller stop
    being the copy every report/listing actually queries.
    """
    profile = instance.user.profile
    update_fields = []
    if (
        profile.role != UserProfile.Role.SELLER
        or profile.tenant_id != instance.tenant_id
        or profile.branch_id != instance.branch_id
    ):
        profile.role = UserProfile.Role.SELLER
        profile.tenant = instance.tenant
        profile.branch = instance.branch
        update_fields += ["role", "tenant", "branch"]
    if profile.full_name != instance.full_name or profile.phone != instance.phone:
        profile.full_name = instance.full_name
        profile.phone = instance.phone
        update_fields += ["full_name", "phone"]
    if update_fields:
        profile.save(update_fields=update_fields)

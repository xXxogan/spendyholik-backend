"""factory_boy factories for test data."""

from __future__ import annotations

import factory

from accounts.infrastructure.orm.models import Profile, User
from finances.infrastructure.orm.models import Account, Category, Transaction


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if extracted:
            self.set_password(extracted)
            if create:
                self.save()


class ProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Profile

    user = factory.SubFactory(UserFactory)


class AccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Account

    user = factory.SubFactory(UserFactory)
    name = factory.Faker("word")
    type = "debit"
    currency = "RUB"


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    user = factory.SubFactory(UserFactory)
    name = factory.Faker("word")
    type = "expense"


class TransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transaction

    user = factory.SubFactory(UserFactory)
    account = factory.SubFactory(AccountFactory)
    type = "expense"
    amount = 100
    date = factory.Faker("date_object")

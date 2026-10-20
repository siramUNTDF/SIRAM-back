from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Organismo, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'rol', 'organismo', 'is_active')
    list_filter = ('rol', 'organismo', 'is_active')
    fieldsets = UserAdmin.fieldsets + (('SIRAM', {'fields': ('rol', 'organismo', 'telefono')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('SIRAM', {'fields': ('rol', 'organismo', 'telefono', 'email')}),)


@admin.register(Organismo)
class OrganismoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo')
    list_filter = ('tipo', 'activo')

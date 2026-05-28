from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from .models import Problem, TeamProgress, HackathonState, BonusQuestion, BonusSubmission
from django.contrib.auth.models import User


@admin.register(HackathonState)
class StateAdmin(admin.ModelAdmin):
    list_display = ('is_started', 'is_finished', 'start_time', 'tutorial_is_started', 'tutorial_is_finished')
    actions = ['start_hackathon_action', 'stop_hackathon_action', 'start_tutorial_action', 'stop_tutorial_action']
    fieldsets = (
        ('Official Hackathon', {'fields': ('is_started', 'is_finished', 'start_time')}),
        ('Tutorial Round', {'fields': ('tutorial_is_started', 'tutorial_is_finished', 'tutorial_start_time')}),
        ('Feature Flags', {'fields': ('hints_enabled',)}),
    )

    def has_add_permission(self, request):
        return not HackathonState.objects.exists()

    def start_hackathon_action(self, request, queryset):
        for state in queryset:
            state.is_started = True
            state.is_finished = False
            state.start_time = timezone.now()
            state.save()
        self.message_user(request, '🚀 Official hackathon started!', messages.SUCCESS)
    start_hackathon_action.short_description = '🚀 Start official hackathon now'

    def stop_hackathon_action(self, request, queryset):
        for state in queryset:
            state.is_finished = True
            state.save()
        self.message_user(request, '🛑 Hackathon stopped!', messages.WARNING)
    stop_hackathon_action.short_description = '🛑 Stop official hackathon'

    def start_tutorial_action(self, request, queryset):
        for state in queryset:
            state.tutorial_is_started = True
            state.tutorial_is_finished = False
            state.tutorial_start_time = timezone.now()
            state.save()
        self.message_user(request, '📚 Tutorial round started!', messages.SUCCESS)
    start_tutorial_action.short_description = '📚 Start tutorial round now'

    def stop_tutorial_action(self, request, queryset):
        for state in queryset:
            state.tutorial_is_finished = True
            state.save()
        self.message_user(request, '📚 Tutorial round stopped.', messages.WARNING)
    stop_tutorial_action.short_description = '📚 Stop tutorial round'


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'difficulty', 'points', 'is_hidden', 'is_tutorial', 'function_name')
    list_filter = ('difficulty', 'is_hidden', 'is_tutorial')
    search_fields = ('title', 'description')
    list_editable = ('difficulty', 'points', 'is_hidden', 'is_tutorial')
    ordering = ('id',)
    fieldsets = (
        ('Problem Info', {'fields': ('title', 'difficulty', 'description', 'examples')}),
        ('Scoring', {'fields': ('points', 'base_points')}),
        ('Code', {'fields': ('function_name', 'input_variable', 'starter_code')}),
        ('Test Cases', {'fields': ('hidden_test_cases',)}),
        ('Visibility', {'fields': ('is_hidden', 'is_tutorial')}),
    )


@admin.register(TeamProgress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ('team', 'problem', 'points', 'is_solved')
    list_filter = ('is_solved', 'problem')
    search_fields = ('team__username',)
    list_editable = ('points',)
    actions = ['reset_progress_action']

    def reset_progress_action(self, request, queryset):
        queryset.update(points=0, is_solved=False, current_code='')
        self.message_user(request, f'Reset {queryset.count()} progress entries.', messages.WARNING)
    reset_progress_action.short_description = '🔄 Reset selected progress'


@admin.register(BonusQuestion)
class BonusAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'appear_after_minutes', 'max_points', 'max_winners', 'duration_minutes')
    list_editable = ('is_active',)
    actions = ['reset_bonus_action']
    fieldsets = (
        ('Question', {'fields': ('title', 'description', 'starter_code', 'expected_output', 'input_type_hint')}),
        ('Timing', {'fields': ('appear_after_minutes', 'duration_minutes')}),
        ('Scoring', {'fields': ('max_points', 'points_step', 'max_winners')}),
        ('Status', {'fields': ('is_active', 'activated_at')}),
    )
    readonly_fields = ()

    def has_add_permission(self, request):
        return not BonusQuestion.objects.exists()

    def reset_bonus_action(self, request, queryset):
        queryset.update(is_active=False, activated_at=None)
        self.message_user(request, '🔄 Bonus reset — activated_at cleared. You can now re-activate it fresh.', messages.SUCCESS)
    reset_bonus_action.short_description = '🔄 Reset bonus (clear activated_at)'


@admin.register(BonusSubmission)
class BonusSubmissionAdmin(admin.ModelAdmin):
    list_display = ('team', 'bonus', 'is_correct', 'points_awarded', 'submitted_at')
    list_filter = ('is_correct',)
    search_fields = ('team__username',)
    readonly_fields = ('team', 'bonus', 'submitted_input', 'is_correct', 'points_awarded', 'submitted_at')


# Branding
admin.site.site_header = 'DIS Hackathon Admin'
admin.site.site_title = 'DIS Admin'
admin.site.index_title = 'Control Panel'

# Inject hackathon state into admin index for quick overview
original_index = admin.site.index
def custom_index(request, extra_context=None):
    if extra_context is None:
        extra_context = {}
    extra_context['h_state'] = HackathonState.objects.first()
    extra_context['b_state'] = BonusQuestion.objects.first()
    extra_context['teams'] = User.objects.filter(is_staff=False).order_by('username')
    return original_index(request, extra_context)
admin.site.index = custom_index
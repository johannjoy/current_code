from urllib import request

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum
from .models import Problem, TeamProgress, HackathonState, BonusQuestion, BonusSubmission
from .utils import run_python_code
from django.utils import timezone
from datetime import timedelta
from django.db.models import Case, When, IntegerField
@login_required
def leaderboard(request):
    state = HackathonState.objects.first()
    if not state:
        return redirect('waiting_room')
    if state.is_finished:
        return redirect('finished')
    if not state.is_started:
        return redirect('waiting_room')

    # Regular points from problems
    team_scores = TeamProgress.objects.filter(
        team__is_staff=False
    ).values('team__username').annotate(
        problem_score=Sum('points')
    )

    # Bonus points
    bonus_scores = BonusSubmission.objects.filter(
        is_correct=True
    ).values('team__username').annotate(
        bonus_score=Sum('points_awarded')
    )

    # Merge into a dict
    bonus_map = {b['team__username']: b['bonus_score'] for b in bonus_scores}

    teams = []
    for t in team_scores:
        username = t['team__username']
        total = (t['problem_score'] or 0) + bonus_map.get(username, 0)
        teams.append({'team__username': username, 'total_score': total})

    # Sort by total
    teams = sorted(teams, key=lambda x: x['total_score'], reverse=True)

    start_time = state.start_time
    end_time = start_time + timedelta(hours=2)
    return render(request, 'leaderboard.html', {
        'teams': teams,
        'end_time': end_time.isoformat()
    })
@login_required
def leaderboard_data(request):
    from django.contrib.auth.models import User
    team_scores = TeamProgress.objects.filter(
        team__is_staff=False
    ).values('team__username').annotate(problem_score=Sum('points'))
    bonus_scores = BonusSubmission.objects.filter(
        is_correct=True
    ).values('team__username').annotate(bonus_score=Sum('points_awarded'))
    bonus_map = {b['team__username']: b['bonus_score'] for b in bonus_scores}
    score_map = {t['team__username']: t['problem_score'] or 0 for t in team_scores}
    all_teams = User.objects.filter(is_staff=False).values_list('username', flat=True)
    teams = []
    for username in all_teams:
        total = score_map.get(username, 0) + bonus_map.get(username, 0)
        teams.append({'username': username, 'total_score': total})
    teams = sorted(teams, key=lambda x: x['total_score'], reverse=True)
    return JsonResponse({'teams': teams})

@login_required
def waiting_room(request):
    state = HackathonState.objects.first()
    if state and state.is_started and not state.is_finished:
        return redirect('home')
    if state and state.is_finished:
        return redirect('finished')
    return render(request, 'waiting_room.html')


@login_required
def home(request):
    state = HackathonState.objects.first()

    if not state:
        return redirect('waiting_room')

    if state.is_finished:
        return redirect('finished')

    if not state.is_started:
        return redirect('waiting_room')

    problems = Problem.objects.all().order_by(
    Case(
        When(difficulty='Easy', then=0),
        When(difficulty='Medium', then=1),
        When(difficulty='Hard', then=2),
        output_field=IntegerField()
    )
)

    bonus_points = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
    total_score = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user)) + bonus_points
    solved_count = TeamProgress.objects.filter(team=request.user, is_solved=True).count()
    # 🔥 ADD THIS
    end_time = state.start_time + timedelta(hours=2)


    solved_ids = set(TeamProgress.objects.filter(team=request.user, is_solved=True).values_list('problem_id', flat=True))

    return render(request, 'home.html', {
        'problems': problems,
        'total_score': total_score,
        'solved_count': solved_count,
        'end_time': end_time.isoformat(),
        'solved_ids': solved_ids,
    })

@login_required
def problem_detail(request, problem_id):
    state = HackathonState.objects.first()
    if not state:
        return redirect('waiting_room')

    if state.is_finished:
        return redirect('finished')

    if not state.is_started:
        return redirect('waiting_room')

    end_time = state.start_time + timedelta(hours=2)
    problem = get_object_or_404(Problem, id=problem_id)
    progress, created = TeamProgress.objects.get_or_create(
    team=request.user,
    problem=problem
)

    if created:
        progress.current_code = problem.starter_code
        progress.save()
    bonus_points = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
    total_score = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user)) + bonus_points
    # Logic for navigation arrows
    prev_id = problem_id - 1 if problem_id > 1 else None
    next_id = problem_id + 1 if problem_id < 15 else None # Assuming 15 problems total

    return render(request, 'problem.html', {
        'end_time': end_time.isoformat(),
        'problem': problem, 
        'progress': progress, 
        'total_score': total_score,
        'prev_id': prev_id,
        'next_id': next_id
    })

# API for Save/Load/Submit
@login_required
def save_code(request):
    if request.method == "POST":
        p_id = request.POST.get('problem_id')
        code = request.POST.get('code')
        TeamProgress.objects.filter(team=request.user, problem_id=p_id).update(current_code=code)
        return JsonResponse({'status': 'Saved'})

@login_required
def load_code(request, problem_id):
    progress = TeamProgress.objects.get(team=request.user, problem_id=problem_id)
    return JsonResponse({'code': progress.current_code})

@login_required
def submit_code(request):
    if request.method == "POST":
        p_id = request.POST.get('problem_id')
        user_code = request.POST.get('code')
        problem = get_object_or_404(Problem, id=p_id)
        if 'import' in user_code:
            return JsonResponse({
                'status': 'Runtime Error',
                'error': 'Import statements are not allowed.'
            })
        progress = get_object_or_404(TeamProgress, team=request.user, problem=problem)
        state = HackathonState.objects.first()
        
        # 1. Run Hidden Test Cases
        for case in problem.hidden_test_cases:
            try:
                input_data = case['input']   # 👈 string input
                expected = case['expected']

                output, error = run_python_code(user_code, input_data, inject_var=problem.input_variable)

                if error:
                    return JsonResponse({
                        'status': 'Runtime Error',
                        'error': error
                    })

                if output.strip() != str(expected).strip():
                    return JsonResponse({'status': 'Wrong Answer'})

            except Exception as e:
                return JsonResponse({
                    'status': 'Runtime Error',
                    'error': str(e)
                })



        # 2. If it reaches here, all cases passed
        if not progress.is_solved:
            # Calculate points: Base - (minutes elapsed)
            elapsed = (timezone.now() - state.start_time).total_seconds()
            time_penalty = int(elapsed / 120)
            final_points = max(20, problem.base_points - time_penalty)
            
            progress.points = final_points
            progress.is_solved = True
            progress.save()

        # 3. Get total team score to update the header
        new_total = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user))
        
        return JsonResponse({
            'status': 'Correct Answer!', 
            'new_total': new_total
        })

@login_required
def bonus_status(request):
    state = HackathonState.objects.first()
    if not state or not state.start_time:
        return JsonResponse({'available': False})

    bonus = BonusQuestion.objects.first()
    if not bonus or not bonus.is_active:
        return JsonResponse({'available': False})

    elapsed_minutes = (timezone.now() - state.start_time).total_seconds() / 60
    if elapsed_minutes < bonus.appear_after_minutes:
        return JsonResponse({'available': False})

    # Set activated_at only once, never reset it
    if not bonus.activated_at:
        bonus.activated_at = timezone.now()
        bonus.save()

    open_seconds = (timezone.now() - bonus.activated_at).total_seconds()
    duration_seconds = bonus.duration_minutes * 60

    winners_so_far = BonusSubmission.objects.filter(bonus=bonus, is_correct=True).count()
    
    # Use integer comparison to avoid float flickering near boundary
    time_expired = open_seconds >= duration_seconds
    spots_full = winners_so_far >= bonus.max_winners
    expired = time_expired or spots_full

    already_solved = BonusSubmission.objects.filter(
        bonus=bonus, team=request.user, is_correct=True
    ).exists()

    already_submitted = BonusSubmission.objects.filter(
        bonus=bonus, team=request.user
    ).exists()

    time_remaining_seconds = max(0, int(duration_seconds - open_seconds))

    # Available = not expired AND user hasn't submitted yet (right or wrong)
    available = not expired and not already_submitted

    return JsonResponse({
        'available': available,
        'expired': expired,
        'already_solved': already_solved,
        'already_submitted': already_submitted,
        'title': bonus.title,
        'description': bonus.description,
        'starter_code': bonus.starter_code,
        'input_type_hint': bonus.input_type_hint,
        'winners_so_far': winners_so_far,
        'max_winners': bonus.max_winners,
        'max_points': bonus.max_points,
        'points_step': bonus.points_step,
        'points_if_next': max(0, bonus.max_points - (winners_so_far * bonus.points_step)),
        'time_remaining_seconds': time_remaining_seconds,
        'duration_minutes': bonus.duration_minutes,
    })
@login_required
def bonus_submit(request):
    if request.method != "POST":
        return JsonResponse({'status': 'error'})

    bonus = BonusQuestion.objects.first()
    if not bonus or not bonus.is_active:
        return JsonResponse({'status': 'Bonus not active'})

    if BonusSubmission.objects.filter(bonus=bonus, team=request.user, is_correct=True).exists():
        return JsonResponse({'status': 'Already submitted'})

    winners_so_far = BonusSubmission.objects.filter(bonus=bonus, is_correct=True).count()
    if winners_so_far >= bonus.max_winners:
        return JsonResponse({'status': 'Bonus closed — all spots taken'})

    if bonus.activated_at:
        open_minutes = (timezone.now() - bonus.activated_at).total_seconds() / 60
        if open_minutes >= bonus.duration_minutes:
            return JsonResponse({'status': 'Bonus round has expired'})

    user_input = request.POST.get('user_input', '').strip()
    output, error = run_python_code(bonus.starter_code, user_input)

    if error:
        return JsonResponse({'status': 'Runtime Error', 'error': error})

    is_correct = output.strip() == bonus.expected_output.strip()
    points_awarded = 0

    if is_correct:
        winners_so_far = BonusSubmission.objects.filter(bonus=bonus, is_correct=True).count()
        if winners_so_far < bonus.max_winners:
            points_awarded = max(0, bonus.max_points - (winners_so_far * bonus.points_step))

    if not is_correct:
        return JsonResponse({'status': 'Wrong Answer — check your input format.'})

    BonusSubmission.objects.create(
        team=request.user, bonus=bonus,
        submitted_input=user_input,
        is_correct=True,
        points_awarded=points_awarded,
    )

    if is_correct and points_awarded > 0:
        new_total = (
            sum(tp.points for tp in TeamProgress.objects.filter(team=request.user))
            + (BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0)
        )
        return JsonResponse({'status': 'Correct!', 'points_awarded': points_awarded, 'new_total': new_total})
    elif is_correct:
        return JsonResponse({'status': 'Correct! But all point slots were just taken.'})
    else:
        return JsonResponse({'status': 'Wrong Answer — check your input format.'})
@login_required
def check_hackathon_status(request):
    state = HackathonState.objects.first()

    if not state or not state.start_time:
        return JsonResponse({
            'is_finished': False,
            'is_live': False
        })

    end_time = state.start_time + timedelta(hours=2)

    if timezone.now() >= end_time:
        state.is_finished = True
        state.save()

    is_finished = state.is_finished
    is_live = state.is_started and not state.is_finished

    return JsonResponse({
        'is_finished': is_finished,
        'is_live': is_live
    })
@login_required
def run_code_custom(request):
    if request.method == "POST":
        user_code = request.POST.get('code')
        # This runs the code without any hidden variables injected
        output, error = run_python_code(user_code)
        return JsonResponse({'output': output, 'error': error})
@login_required
def finished(request):
    state = HackathonState.objects.first()
    if state and state.is_started and not state.is_finished:
        return redirect('home')
    bonus_points = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
    total_score = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user)) + bonus_points
    return render(request, 'finished.html', {'total_score': total_score})
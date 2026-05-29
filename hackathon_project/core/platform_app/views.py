from urllib import request
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum
from django.db import transaction
from .models import Problem, TeamProgress, HackathonState, BonusQuestion, BonusSubmission
from .utils import run_python_code
from django.utils import timezone
from django.utils import timezone as tz
from datetime import timedelta
from django.db.models import Case, When, IntegerField
import json
import urllib.request as urlreq
import urllib.error
@login_required
def leaderboard(request):
    state = HackathonState.objects.first()
    if not state:
        return redirect('waiting_room')
    if state.is_finished:
        return redirect('finished')
        
    # 1. This lets users in if the tutorial is running
    tutorial_active = state.tutorial_is_started and not state.tutorial_is_finished
    if not state.is_started and not tutorial_active:
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

    # 2. FIXED TIME MATH: Calculates the correct countdown clock safely
    if tutorial_active:
        start_time = state.tutorial_start_time or timezone.now()
        end_time = start_time + timedelta(minutes=20)
    else:
        start_time = state.start_time or timezone.now()
        end_time = start_time + timedelta(hours=2)

    # Prevent potential timezone offset rendering issues
    from django.utils import timezone as tz
    if end_time.tzinfo is None:
        end_time = tz.make_aware(end_time)

    return render(request, 'leaderboard.html', {
        'teams': teams,
        'end_time': end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
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
    if state and state.tutorial_is_started and not state.tutorial_is_finished:
        return redirect('home')
    return render(request, 'waiting_room.html')


@login_required
def home(request):
    state = HackathonState.objects.first()
    if not state:
        return redirect('waiting_room')
    if state.is_finished:
        return redirect('finished')

    # Determine active mode
    tutorial_active = state.tutorial_is_started and not state.tutorial_is_finished
    official_active = state.is_started and not state.is_finished

    if not official_active and not tutorial_active:
        return redirect('waiting_room')

    if tutorial_active:
        problems = Problem.objects.filter(is_hidden=False, is_tutorial=True).order_by(
            Case(When(difficulty='Easy', then=0), When(difficulty='Medium', then=1), When(difficulty='Hard', then=2), output_field=IntegerField())
        )
        from django.utils import timezone as tz
        start = state.tutorial_start_time
        if start.tzinfo is None:
            start = tz.make_aware(start)
        end_time = start + timedelta(minutes=20)
        mode = 'tutorial'
    else:
        problems = Problem.objects.filter(is_hidden=False, is_tutorial=False).order_by(
            Case(When(difficulty='Easy', then=0), When(difficulty='Medium', then=1), When(difficulty='Hard', then=2), output_field=IntegerField())
        )
        from django.utils import timezone as tz
        start = state.start_time
        if start.tzinfo is None:
            start = tz.make_aware(start)
        end_time = start + timedelta(hours=2)
        mode = 'official'

    bonus_points = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
    total_score = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user)) + bonus_points
    solved_count = TeamProgress.objects.filter(team=request.user, is_solved=True).count()
    solved_ids = set(TeamProgress.objects.filter(team=request.user, is_solved=True).values_list('problem_id', flat=True))

    return render(request, 'home.html', {
        'problems': problems,
        'total_score': total_score,
        'solved_count': solved_count,
        'end_time': end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'solved_ids': solved_ids,
        'mode': mode,
    })
@login_required
def problem_detail(request, problem_id):
    state = HackathonState.objects.first()
    if not state:
        return redirect('waiting_room')
    if state.is_finished:
        return redirect('finished')

    tutorial_active = state.tutorial_is_started and not state.tutorial_is_finished
    official_active = state.is_started and not state.is_finished

    if not official_active and not tutorial_active:
        return redirect('waiting_room')

    if tutorial_active:
        from django.utils import timezone as tz
        start = state.tutorial_start_time
        if start.tzinfo is None:
            start = tz.make_aware(start)
        end_time = start + timedelta(minutes=20)
        mode = 'tutorial'
    else:
        start = state.start_time
        if start.tzinfo is None:
            start = tz.make_aware(start)
        end_time = start + timedelta(hours=2)
        mode = 'official'

    problem = get_object_or_404(Problem, id=problem_id, is_hidden=False)
    progress, created = TeamProgress.objects.get_or_create(team=request.user, problem=problem)
    if created:
        progress.current_code = problem.starter_code
        progress.save()

    bonus_points = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
    total_score = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user)) + bonus_points
    all_problem_ids = list(Problem.objects.filter(is_hidden=False).order_by('id').values_list('id', flat=True))
    current_index = all_problem_ids.index(problem_id) if problem_id in all_problem_ids else -1
    prev_id = all_problem_ids[current_index - 1] if current_index > 0 else None
    next_id = all_problem_ids[current_index + 1] if current_index != -1 and current_index < len(all_problem_ids) - 1 else None

    return render(request, 'problem.html', {
        'end_time': end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'problem': problem,
        'progress': progress,
        'total_score': total_score,
        'prev_id': prev_id,
        'next_id': next_id,
        'mode': mode,
    })

# API for Save/Load/Submit
@login_required
def save_code(request):
    if request.method == "POST":
        p_id = request.POST.get('problem_id')
        code = request.POST.get('code')
        TeamProgress.objects.filter(team=request.user, problem_id=p_id).update(current_code=code)
        return JsonResponse({'status': 'Saved'})
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

@login_required
def load_code(request, problem_id):
    try:
        progress = TeamProgress.objects.get(team=request.user, problem_id=problem_id)
        return JsonResponse({'code': progress.current_code})
    except TeamProgress.DoesNotExist:
        return JsonResponse({'code': ''})

@login_required
def submit_code(request):
    if request.method == "POST":
        p_id = request.POST.get('problem_id')
        user_code = request.POST.get('code')
        problem = get_object_or_404(Problem, id=p_id)
        
        progress = get_object_or_404(TeamProgress, team=request.user, problem=problem)
        state = HackathonState.objects.first()
        
        # 1. Run Hidden Test Cases
        for case in problem.hidden_test_cases:
            try:
                input_data = case['input']   
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
        with transaction.atomic():
            progress = TeamProgress.objects.select_for_update().get(team=request.user, problem=problem)
            if not progress.is_solved:
                tutorial_active = state.tutorial_is_started and not state.tutorial_is_finished if state else False
                
                if tutorial_active:
                    final_points = 0
                else:
                    start_time = state.start_time if (state and state.start_time) else timezone.now()
                    if start_time.tzinfo is None:
                        start_time = tz.make_aware(start_time)
                    elapsed = (timezone.now() - start_time).total_seconds()
                    time_penalty = int(elapsed / 120)
                    final_points = max(20, problem.base_points - time_penalty)
                
                progress.is_solved = True
                progress.points = final_points
                progress.current_code = user_code
                progress.save()

                bonus_pts = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
                total_score = TeamProgress.objects.filter(team=request.user).aggregate(s=Sum('points'))['s'] or 0
                total_score += bonus_pts

                return JsonResponse({'status': 'Accepted', 'points': final_points, 'total_score': total_score})
            
        return JsonResponse({'status': 'Already Solved'})
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

@login_required
def bonus_status(request):
    state = HackathonState.objects.first()
    if not state or not state.start_time:
        return JsonResponse({'available': False})

    bonus = BonusQuestion.objects.first()
    if not bonus or not bonus.is_active:
        return JsonResponse({'available': False})

    bonus_start = state.start_time
    if bonus_start.tzinfo is None:
        bonus_start = tz.make_aware(bonus_start)
    elapsed_minutes = (timezone.now() - bonus_start).total_seconds() / 60
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

    bonus = BonusQuestion.objects.filter(is_active=True).first()
    if not bonus:
        return JsonResponse({'status': 'Bonus not active'})

    if BonusSubmission.objects.filter(bonus=bonus, team=request.user, is_correct=True).exists():
        return JsonResponse({'status': 'Already submitted'})

    if bonus.activated_at:
        open_minutes = (timezone.now() - bonus.activated_at).total_seconds() / 60
        if open_minutes >= bonus.duration_minutes:
            return JsonResponse({'status': 'Bonus round has expired'})

    user_input = request.POST.get('user_input', '').strip()
    output, error = run_python_code(bonus.starter_code, user_input)

    if error:
        return JsonResponse({'status': 'Runtime Error', 'error': error})

    is_correct = output.strip() == bonus.expected_output.strip()

    if not is_correct:
        return JsonResponse({'status': 'Wrong Answer — check your input format.'})

    with transaction.atomic():
        # Lock all existing correct submissions for this bonus to prevent race
        winners_so_far = BonusSubmission.objects.select_for_update().filter(bonus=bonus, is_correct=True).count()
        if winners_so_far >= bonus.max_winners:
            return JsonResponse({'status': 'Bonus closed — all spots taken'})

        points_awarded = max(0, bonus.max_points - (winners_so_far * bonus.points_step))

        BonusSubmission.objects.create(
            team=request.user, bonus=bonus,
            submitted_input=user_input,
            is_correct=True,
            points_awarded=points_awarded,
        )

    if points_awarded > 0:
        new_total = (
            sum(tp.points for tp in TeamProgress.objects.filter(team=request.user))
            + (BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0)
        )
        return JsonResponse({'status': 'Correct!', 'points_awarded': points_awarded, 'new_total': new_total})
    else:
        return JsonResponse({'status': 'Correct! But all point slots were just taken.'})
@login_required
def check_hackathon_status(request):
    state = HackathonState.objects.first()
    if not state or not state.start_time:
        # Check tutorial
        if state and state.tutorial_is_started and not state.tutorial_is_finished and state.tutorial_start_time:
            tut_start = state.tutorial_start_time
            if tut_start.tzinfo is None:
                tut_start = tz.make_aware(tut_start)
            tutorial_end = tut_start + timedelta(minutes=20)
            if timezone.now() >= tutorial_end:
                state.tutorial_is_finished = True
                state.save()
                return JsonResponse({'is_finished': False, 'is_live': False, 'tutorial_live': False, 'tutorial_finished': True})
            return JsonResponse({'is_finished': False, 'is_live': False, 'tutorial_live': True, 'tutorial_finished': False})
        return JsonResponse({'is_finished': False, 'is_live': False, 'tutorial_live': False, 'tutorial_finished': False})

    off_start = state.start_time
    if off_start.tzinfo is None:
        off_start = tz.make_aware(off_start)
    end_time = off_start + timedelta(hours=2)
    if timezone.now() >= end_time:
        state.is_finished = True
        state.save()

    # Check tutorial timeout too
    if state.tutorial_is_started and not state.tutorial_is_finished and state.tutorial_start_time:
        tut_start2 = state.tutorial_start_time
        if tut_start2.tzinfo is None:
            tut_start2 = tz.make_aware(tut_start2)
        tutorial_end = tut_start2 + timedelta(minutes=20)
        if timezone.now() >= tutorial_end:
            state.tutorial_is_finished = True
            state.save()

    tutorial_live = state.tutorial_is_started and not state.tutorial_is_finished and not state.is_started

    return JsonResponse({
        'is_finished': state.is_finished,
        'is_live': state.is_started and not state.is_finished,
        'tutorial_live': tutorial_live,
        'tutorial_finished': state.tutorial_is_finished,
    })
@login_required
def run_code_custom(request):
    if request.method == "POST":
        user_code = request.POST.get('code')
        if not user_code:
            return JsonResponse({'output': None, 'error': 'No code provided'})
        output, error = run_python_code(user_code)
        return JsonResponse({'output': output, 'error': error})
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)
@login_required
def finished(request):
    state = HackathonState.objects.first()
    # Only show finished page if the official hackathon actually ran and is done
    if not state or not state.is_started:
        return redirect('waiting_room')
    if state.is_started and not state.is_finished:
        return redirect('home')
    bonus_points = BonusSubmission.objects.filter(team=request.user, is_correct=True).aggregate(s=Sum('points_awarded'))['s'] or 0
    total_score = sum(tp.points for tp in TeamProgress.objects.filter(team=request.user)) + bonus_points
    return render(request, 'finished.html', {'total_score': total_score})
@login_required
def ai_hint(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    state = HackathonState.objects.first()
    if not state or not state.hints_enabled:
        return JsonResponse({'hint': 'AI hints have been disabled by your instructor.'})

    problem_id = request.POST.get('problem_id')
    current_code = request.POST.get('code', '')
    console_output = request.POST.get('console_output', '').strip()
    problem = get_object_or_404(Problem, id=problem_id)

    cache_key = f'hint_used_{request.user.id}_{problem_id}'
    from django.core.cache import cache
    if cache.get(cache_key):
        return JsonResponse({'hint': '⚠️ You have already used your hint for this problem.', 'already_used': True})
    cache.set(cache_key, True, timeout=60*60*3)

    from django.conf import settings
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        return JsonResponse({'hint': 'API key not configured. Contact admin.'})

    code_block = current_code.strip() or '(empty — student has not written anything yet)'

    if console_output:
        console_section = '\n\nLatest console output or error:\n' + console_output + '\nIf this shows an error or wrong answer, address it in your hint.'
    else:
        console_section = ''

    prompt = (
        "You are a helpful coding tutor for a Python hackathon. Help the student with this problem.\n\n"
        "Problem: " + problem.title + "\n"
        "Description: " + problem.description + "\n\n"
        "Student's current code:\n" + code_block + "\n"
        + console_section + "\n\n"
        "Give a helpful hint to guide them toward the solution WITHOUT giving away the full answer. "
        "Be encouraging, concise (2-4 sentences max), and specific to their code and any errors shown. "
        "Focus on the approach or algorithm, not the exact implementation."
    )

    payload = json.dumps({
        'model': 'llama-3.3-70b-versatile',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 300,
        'temperature': 0.7,
    }).encode()

    req = urlreq.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Mozilla/5.0',
        },
        method='POST'
    )

    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            hint_text = data['choices'][0]['message']['content']
            return JsonResponse({'hint': hint_text})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='ignore')
        return JsonResponse({'hint': f'API error {e.code}: {body}'})
    except Exception as e:
        return JsonResponse({'hint': f'Could not load hint: {e}'})
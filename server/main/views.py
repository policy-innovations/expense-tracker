from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.template import RequestContext
from django.utils import simplejson
from django.utils.functional import curry
from django.forms.formsets import formset_factory

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, check_password

from excel_response import ExcelResponse
from main.models import *
from main.forms import PersonalExpenseForm, OfficialExpenseForm

from datetime import datetime
import settings

@login_required
def home(request):
    """
    Personal expenses
    """
    expenses = Expense.objects.filter(token__user=request.user,
                                      type=PERSONAL).order_by('-time')
    p = Paginator(expenses, 10)
    page = p.page(request.GET.get('p', 1))
    PExpFormset = formset_factory(PersonalExpenseForm)
    if request.method == 'POST':
        formset = PExpFormset(request.POST, request.FILES)

        if formset.is_valid():
            for form in formset:
                expense = Expense(**form.cleaned_data)
                # Get the auth token for website
                token = AuthToken.objects.get_or_create(user=request.user,
                                                        site_token=True)[0]
                expense.token = token
                expense.save()

            return redirect('/')
    else:
        initial = {
        }
        try:
            # The initial data
            latest = expenses.latest()
            initial['location'] = latest.location
            initial['category']=latest.category

        except Expense.DoesNotExist:
            pass

        # Use the curry utility to pass initial data to forms in
        # the formset
        PExpFormset.form = staticmethod(curry(PersonalExpenseForm,
                                              initial=initial))
        formset = PExpFormset()

    return render(request, 'main/home.html', {'page': page,
                                             'formset':formset})

@login_required
def organisation(request, org_pk):
    """
    Expenses for organisation
    """
    org = Organisation.objects.get(pk=org_pk)
    expenses = Expense.objects.filter(token__user=request.user,
                                      project__organisation=org).order_by('-time')
    p = Paginator(expenses, 10)
    page = p.page(request.GET.get('p', 1))

    OExpFormset = formset_factory(OfficialExpenseForm)
    # Use curry to get the form specifically for the organisation
    OExpFormset.form = staticmethod(curry(OfficialExpenseForm, org))

    if request.method == 'POST':
        formset = OExpFormset(request.POST, request.FILES)

        if formset.is_valid():
            for form in formset:
                expense = form.save(commit=False)
                token = AuthToken.objects.get_or_create(user=request.user,
                                                    site_token=True)[0]
                expense.token = token
                if expense.billed:
                    # If expense is billed, create a bill ID in this format:
                    # <user_id><proj_id><token_id><count>
                    expense.bill_id = '%s%s%s%s' %(token.user.id, expense.project.id,
                                                   token.id,
                                                   expenses.filter(token=token,
                                                                    billed=True).count()+1)
                expense.save()

            return redirect(org)
    else:
        initial = {
        }
        try:
            # Fill up the initial data
            latest = expenses.latest()
            initial['location'] = latest.location
            initial['category']=latest.category
            initial['project']=latest.project

        except Expense.DoesNotExist:
            pass

        # Use the curry utility to pass initial data to forms in
        # the formset
        OExpFormset.form = staticmethod(curry(OfficialExpenseForm, org,
                                              initial=initial))
        formset = OExpFormset()

    return render(request, 'main/organisation.html', {
                                                'organisation':org,
                                                'page':page,
                                                'formset':formset,
                                            })

def excel_export(request):
    expenses = Expense.objects.filter(project__isnull=False)
    data = [expense.data_tuple() for expense in expenses]
    print data
    return ExcelResponse(data)

def mobile_login(request):
    '''
    Allow mobile devices to login through username and password and get
    the authentication token.
    Format:
    uid|token|projects(csv)|project_ids(csv)|type(csv)|locations(csv)|last bill or empty
    '''
    # Get the use, pass
    username = request.REQUEST.get('u', False)
    password = request.REQUEST.get('p', False)

    try:
        # Look for the user
        user = User.objects.get(username=username)
    except:
        user = None

    # Authenticate
    if not (user and check_password(password, user.password)):
        raise Http404('Invalid username or password supplied.')

    organisation = Organisation.objects.get(pk=1)
    auth_token = AuthToken.objects.create(user=user)

    return HttpResponse(get_sync_data(auth_token), mimetype='text/plain')

def add_expense(request):
    '''
    Allow mobile devices to use authentication token to upload expenses
    to the server
    Format:
    expense: token,place,amount,personal/official,project,type,bill_id,timestamp
    expenses: expense1|expense2|...
    '''
    q = request.GET.get('q', '')
    exp_qs = q.split('|')
    print exp_qs

    expenses = []
    for exp_q in exp_qs:
        exp_q = exp_q.split(',')

        exp_dict = {
                'token':get_object_or_404(AuthToken, key=exp_q[0]),
                'location':get_by_title(Location, exp_q[1]),
                'amount': float(exp_q[2]),
                'project':get_by_title(Project, exp_q[4]),
                'category':get_by_title(Category, exp_q[5]),
                'billed': True if exp_q[6] else False,
                'bill_id': exp_q[6],
                'time': datetime.fromtimestamp(float(exp_q[7])),
                }
        exp_dict['type'] = OFFICIAL if exp_dict['project'] else PERSONAL

        expense = Expense.objects.create(**exp_dict)
        expenses.append(expense)
        response = create_csv(len(expenses))

    return HttpResponse(response, mimetype='text/plain')

def sync(request):
    """
    Provide mobile data updated info, using auth token.
    Gives out same output as a login.
    """
    auth_token = get_object_or_404(AuthToken,
                                   key=request.REQUEST.get('token', False))
    return HttpResponse(get_sync_data(auth_token), mimetype='text/plain')




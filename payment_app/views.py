from django.http.response import HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from .models import *
from django.views.generic import ListView, CreateView, DetailView, TemplateView
import stripe
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json


# This is the home page of our application. 
# We'll display a list of products in the database here.
class ProductListView(ListView):
    model = Product
    template_name = "payment_app/product_list.html"
    '''
    context_object_name - Name of the context object that will hold the list of products. 
    Django will automatically fetch the list of products,
    so that we do not have to write the query to fetch products from the database.
    '''
    context_object_name = 'product_list'


# To create a new Product.
class ProductCreateView(CreateView):
    '''
    The target model.
    '''
    model = Product
    '''
    Fields that will be displayed in the form. The value __all__ indicates 
    that the form should contain fields for 
    all properties of the model. Primary keys and auto fields will be excluded.
    '''
    fields = '__all__'
    '''
    Name of the template that should be rendered. 
    If this property is not set, Django will try to use a default template.
    '''
    template_name = "payment_app/product_create.html"
    '''
    URL of the the page that the user should be 
    redirected to, after saving the form
    '''
    success_url = reverse_lazy("home")


# As the name indicates, this view will be used to display the details of a product.
#  We'll integrate Stripe Payment Gateway to this page.
class ProductDetailView(DetailView):
    model = Product
    template_name = "payment_app/product_detail.html"
    '''
    to instruct Django to fetch details of 
    the product with the id passed as a URL parameter
    '''
    pk_url_kwarg = 'id'
    '''
    to add publishable key as a data to the template context
    '''
    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)
        context['stripe_publishable_key'] = settings.STRIPE_PUBLISHABLE_KEY
        return context 


# This view serves as an API to initialize the payment gateway.
'''
1.Creating a Stripr checkout session using the Stripe Library.
2.Saving the order details along with the payment intent obtained from stripe session.
     You can consider payment intent as a unique identifier for each payments.
3.Return the session ID as JSON data.
To create a new checkout session, we should provide these details.
customer_email - This is an optional field. If specified, this email will be 
                used to identity a customer in Stripe. This email will also be 
                displayed on the payment page.
payment_method_types - Payment methods that the user can
                    use to make payments.  
                        You can read more about payment types here.
line_items - Details about the products that
                 the customer is purchasing. 
                 If you want to learn more about customizing line_items,
                  check the documentation.
unit_amount - Price of the product multiplied by 100. 
                It should be an integer value.
quantity - An integer value that indicates the order count.
success_url - Full URL of that page that the user should be r
                    edirected after a successful payment. 
                    You can use this page to display a success message and mark the order as 
                    completed. Note that I am appending ?session_id={CHECKOUT_SESSION_ID}
                     to the end of the URL. This part tells Stripe to append the checkout 
                     session id as a parameter to the URL of the page, so that we can 
                     identity the payment that was successful and mark the corresponding 
                     order as completed.
cancel_url - Full URL of that page that the user should be
                     redirected if the payment failed for some reason.
mode - Indicates the type of payment. It can be a 
                single payment or a subscription.
'''
@csrf_exempt
def create_checkout_session(request, id):

    request_data = json.loads(request.body)
    product = get_object_or_404(Product, pk=id)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    checkout_session = stripe.checkout.Session.create(
        # Customer Email is optional,
        # It is not safe to accept email directly from the client side
        customer_email = request_data['email'],
        payment_method_types=['card'],
        line_items=[
            {
                'price_data': {
                    'currency': 'inr',
                    'product_data': {
                    'name': product.name,
                    },
                    'unit_amount': int(product.price * 100),
                },
                'quantity': 1,
            }
        ],
        mode='payment',
        success_url=request.build_absolute_uri(
            reverse('success')
        ) + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=request.build_absolute_uri(reverse('failed')),
    )


    order = OrderDetail()
    order.customer_email = request_data['email']
    order.product = product
    order.stripe_payment_intent = checkout_session['payment_intent']
    order.amount = int(product.price * 100)
    order.save()

    # return JsonResponse({'data': checkout_session})
    return JsonResponse({'sessionId': checkout_session.id})


# This is that page that users will be redirected to after successful payment.
class PaymentSuccessView(TemplateView):
    template_name = "payment_app/payment_success.html"

    def get(self, request, *args, **kwargs):
        '''
        session_id obtained from the URL to mark the Order as completed
        '''
        session_id = request.GET.get('session_id')
        if session_id is None:
            return HttpResponseNotFound()
        
        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(session_id)

        order = get_object_or_404(OrderDetail, stripe_payment_intent=session.payment_intent)
        order.has_paid = True
        order.save()
        return render(request, self.template_name)


# This is that page that users will be redirected to if the payment failed.
class PaymentFailedView(TemplateView):
    template_name = "payment_app/payment_failed.html"


# All previous orders and status will be displayed on this page.
class OrderHistoryListView(ListView):
    model = OrderDetail
    template_name = "payment_app/order_history.html"

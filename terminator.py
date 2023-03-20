#!/usr/bin/python3
from telegram.ext import Updater, InlineQueryHandler, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler
from telegram import ReplyKeyboardRemove,ReplyKeyboardMarkup,InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Bot
import requests
import re
from bs4 import BeautifulSoup
import sys
from binascii import a2b_base64
#pip3 install git+https://github.com/codevance/python-deathbycaptcha.git
import deathbycaptcha
import json
from itertools import  cycle
import tempfile
import datetime

#Credentials for DeathByCaptcha
deathbycaptcha_username = 'hmjzbot'
deathbycaptcha_password = 'Z3@-NJ2CpdyugWY'

#The bot is using callbacks from the user to perform some actions. It works with inline keyboard buttons.
#To successfully capture state and handle callback data, state variables are declared here.
#Stages
FIRST, SECOND,THIRD,FOURTH,FIFTH,POST_INFORMATION = range(6)
#Callback data
ONE, TWO, THREE, FOUR = range(4)

#Start function defines bot behaviour when user types the /start command, 1 button menu is generated and callback data is collected for each click
def start(update, context):
    keyboard = [
        [
            InlineKeyboardButton('Anmelden', callback_data=str(ONE)),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    #update.message.reply_text('Hi ' + update.message.from_user.first_name + '! Please choose an option:' , reply_markup=reply_markup)
    update.message.reply_text("Hi! \n I’m a semi-sentient telegram based life-form created to help you get an appointment (termin) in Bürgeramt's of Berlin!" , reply_markup=reply_markup)
    return FIRST

#Define anmelden function that takes care of navigating to the page with calendars and finding available appointments
def anmelden(update, context):
    
    #Create a session and store it in context for the specific user
    session = requests.Session()
    context.user_data['session'] = session
    
    #Create a list for storing all available appointment dates
    all_available_dates = []

    update.callback_query.edit_message_text(text="Searching for available appointments...")  
    url = 'https://service.berlin.de/dienstleistung/120686/'
    data = session.get(url)
    soup = BeautifulSoup(data.text, 'html.parser')
    products = soup.findAll('div', {'class': 'zmstermin-multi inner'})
    
    #Look for "Termin berlinweit suchen" button (url)
    products = soup.findAll('div', {'class': 'zmstermin-multi inner'})
    for p in products:
        link = p.find('a')['href']
        r = session.get(link)
    parseData = BeautifulSoup(r.text, 'html.parser')
    
    #check if there are available dates, display a sorry message  if no dates were found
    #In some cases the dates are available but they are not scraped anyway (sometimes the Burgeramt site blocks the connection).
    #Tough to say what could be done to prevent these situations, it usually fixes on a retry (typing /start again).
    findDates = parseData.findAll('td', {'class': 'buchbar'})
    if len(findDates) == 0:
        print(data.url)
        print(r.url)
        sorryMsg = 'Sorry! There are no available dates.\n Enter /start again to retry.'
        update.callback_query.message.reply_text(sorryMsg)
        return SECOND
    
    else:
        #Declare a counter to distinguish between two visible calendar months and two lists to store months names and appointment urls
        counter = 0
        months = []
        appointment_urls = []
        
        #Find the two months names and store it in a list
        for m in parseData.findAll('th', {'class': 'month'}):
            month = m.text.strip()
            months.append(month)
        
        #Since there are two calendars, we need to store them both in the list
        soup = BeautifulSoup(r.content, "html.parser")
        appointment_list = soup.find_all('div', {'class': 'calendar-month-table span6'})

        #For each calendar, get the available appointment urls, the end goal is to create a key/value pair with appointment date and corresponding URL
        for buchbar in appointment_list:
            all_available = buchbar.find_all('td', {'class': 'buchbar'})
            for buchbar in all_available:
                appointment_url =  buchbar.find_all('a', href=True)
                for j in appointment_url:
                    appointment_urls.append(j['href'])
                    all_available_dates.append((buchbar.text.strip() + ' ' + months[counter], j['href']))
            counter = counter + 1
        
        #Create a dynamic menu with buttons for each appointment date and return FIRST as state
        query = update.callback_query
        query.answer()
        keyboard=[]

        #Display each button  in a newline
        #Callback data is the date itself and it is the same as the text displayed on the button, example: 12 November 2020
        for date,endpoint  in all_available_dates:
            keyboard.insert(len(keyboard), [InlineKeyboardButton(date, callback_data=date)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Please choose your appointment date", reply_markup=reply_markup)
        
        #Debug msg
        print(all_available_dates)
        print(len(all_available_dates))
        context.user_data['all_available_dates'] = all_available_dates
        return FIRST

def appointment_choice(update, context):
    #read session variable value from context
    session = context.user_data['session']
    
    #create an  empty appointment dictionary to store hours and locations
    appointments_dictionary = {}
    all_available_dates = context.user_data['all_available_dates']
    query = update.callback_query
    query.answer()
    
    #query.message.reply_text('yaaay you have found an appointment date')
    query.edit_message_text(text='Selected option: {}.\nPlease wait...'.format(query.data))
    
    #Create an URL based on the endpoint stored in the all_available_dates list
    appointment_endpoint = ''
    for date,endpoint in all_available_dates:
        if query.data == date:
            url_date = 'https://service.berlin.de' + endpoint
            appointment_endpoint = endpoint
    appointment_endpoint = appointment_endpoint.partition("/terminvereinbarung/termin/time/")[2]
    
    #debug message to see if the url is correct, create a session using this url
    print(url_date)
    r = session.get(url_date)
    #Clear the global variable in case something goes wrong and the user retries
    all_available_dates.clear()
    
    #See where the bot is, probably stuck on captcha
    captcha_detected = r.url
    print(captcha_detected)
    parseData = BeautifulSoup(r.text, 'html.parser')
    captcha_passed = False
    if captcha_detected == 'https://service.berlin.de/terminvereinbarung/termin/human/':
        while captcha_passed is False:
            print('Captcha verification... please wait')
            captcha_container = parseData.find('form', {'action': '/terminvereinbarung/termin/human/'})
            captcha_image = captcha_container.find('img')
            captcha_image_url = captcha_image['src']
        
            #The URL looks like this: 'data:image/png;base64,iVBORw0KG...', base64 string is needed to generate the captcha image
            #Using string.partition() you put the string as function argument and then use the index [2] to get the remainder of the string
            #This array has 3 indexes (0,1,2):
            #0 - string that comes before the string from the input (in this case - its an empty string because data:image/png;base64 is the beginning of the string)
            #1 - is the string from the input
            #2 - what comes after the string from the input
            base64_from_url = captcha_image_url.partition("data:image/png;base64,")[2]
            
            #Generate a random filename using tempfile module
            tf = tempfile.NamedTemporaryFile()
            captcha_filename = tf.name
            print(captcha_filename)
            
            #Get the binary data, open the file and write to it
            binary_data = a2b_base64(base64_from_url)
            fd = open(captcha_filename, 'wb')
            fd.write(binary_data)

            #Send the image to DeathByCaptcha
            deathbycaptcha_timeout = 30 #30 second timeout for captcha solving, can be adjusted if it is too short
            deathbycaptcha_client = deathbycaptcha.SocketClient(deathbycaptcha_username, deathbycaptcha_password)
            try:
                captcha_to_resolve = deathbycaptcha_client.decode(captcha_filename, deathbycaptcha_timeout)
                if captcha_to_resolve:
                    print("CAPTCHA %s solved: %s" % (captcha_to_resolve["captcha"], captcha_to_resolve["text"]))
                    resolved_captcha = captcha_to_resolve["text"]
            except deathbycaptcha.AccessDeniedException:
                print('DeathByCaptcha Access DENIED')

            #The captcha form is a GET form so we need to modify the URL here with the right text
            #Example:
            #https://service.berlin.de/terminvereinbarung/termin/human/?captcha_text=hMddiv       
            captcha_getform_url = captcha_detected + '?captcha_text=' + resolved_captcha
            print(captcha_getform_url)
            r = session.get(captcha_getform_url)
            #Debug msg: CHECK CURRENT URL
            print(r.url)
            #For some reason it is redirecting to https://service.berlin.de/terminvereinbarung/termin/time/ and this is
            #not the correct url and the date of the appointment scrapped from this URL is a default date (year 1970)
            #We need to recreate the session with the URL with endpoint, the one just before captcha redirect (variable: url_date)
            
            #Captcha verification is okay when the current url looks exactly like this. Exit the loop, else it will try to resolve the captcha again
            if r.url == 'https://service.berlin.de/terminvereinbarung/termin/time/':
                captcha_passed = True
            
            #Debug: See if the date is correct
            r = session.get(url_date)
            
            parseData = BeautifulSoup(r.text, 'html.parser')
            print(r.url)

    else:
        parseData = BeautifulSoup(r.text, 'html.parser')
        print('NO captcha verification, yaaay!')
    
    #Get the list of all available hours
    available_hours = parseData.findAll('th', {'class': 'buchbar'})
    #Get the list of all available locations
    available_locations = parseData.findAll('td', {'class': 'frei'})
    
    hours = []
    locations = []
    
    #Save all location urls in a seperate list
    location_urls = []
    
    for h in available_hours:
        hour = h.text.strip()
        hours.append(hour)
    for l in available_locations:
        location = l.text.strip()
        locations.append(location)

    #DEBUG MSGs
    print(hours)
    print(locations)
    print('\n\n\n')

    for i in available_locations:
        url = i.find('a')['href']
        location_urls.append(url)

    print(location_urls)
    
    
    #Create a key-value pair of location and location urls
    combined_url_location = []
    location_counter = 0
    for item in locations:
        combined_url_location.append(tuple((item,location_urls[location_counter])))
        location_counter += 1

    #DEBUG MSGs
    print('\n\n\n')
    print(combined_url_location)
    
    #Create a dictionary to store key and values for locations and available hours
    #It is necessary as one hour can hold multiple locations

    hour_cycle = cycle(hours) #Using cycle to get access to next value in a list
    for location in combined_url_location:
         #Get the current value, starting with the 0 index of the hours list
        current_value = next(hour_cycle)
        #If current value is not an empty string (so it is an hour), assign key as a current_value, and the location is the value
        if current_value != '':
            appointments_dictionary[current_value] = [location]
            #Save this key as it is not empty (to write to it again if there are multiple locations for the same hour)
            last_value = current_value
        #If the current value is empty, get the last_value as a key and store the location
        else:
            appointments_dictionary[last_value].append(location)
    
    #DEBUG msg
    print(appointments_dictionary)
    
    #Get only hours from the dictionary
    dictionary_hour_list = []
    for key in appointments_dictionary:
        dictionary_hour_list.append(key)
    print(dictionary_hour_list)
     
    #Create a keyboard with buttons for each hour of the appointment (4 different hours in a row)
    #When user clicks on a specific hour, callback data captures this response 
    keyboard = []
    buttons_per_row = 4
    for i,x in enumerate(dictionary_hour_list):
        if i % buttons_per_row == 0:
            keyboard.insert(len(keyboard), [InlineKeyboardButton(x, callback_data=(x + ' ' + appointment_endpoint))])
        else:
            keyboard[len(keyboard)-1].append(InlineKeyboardButton(x, callback_data=(x + ' ' + appointment_endpoint)))

    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text="Please choose appointment time:", reply_markup=reply_markup)
    context.user_data['appointments_dictionary'] = appointments_dictionary

    return FIRST

def location_choice(update, context):
    #Read session value and dictionary from context
    session = context.user_data['session']
    appointments_dictionary = context.user_data['appointments_dictionary']
    query = update.callback_query
    query.answer()
    query.edit_message_text(text='Selected option: {}'.format(query.data))
    callback = query.data
    
    #As callback data looks like this (example): '12:00 1610319600/' we need to extract hour only
    chosen_hour = callback.split()[0]
    
    #Recreate url_date value from callback data - needed to get to the same point on the website as in appointment_choice function
    url_date = 'https://service.berlin.de/terminvereinbarung/termin/time/' + callback.split()[1]
    
    #Debug MSGs
    print(chosen_hour)
    print(url_date)

    #Get all available locations based on the hour chosen by user
    locations_for_chosen_hour = []
    for location in appointments_dictionary[chosen_hour]:
        locations_for_chosen_hour.append(location)

    #Debug MSG
    print(locations_for_chosen_hour)

    #Create a keyboard with 1 button with location per row
    #Callback data is the location url endpoint, looks like this: /terminvereinbarung/termin/time/1610363880/898/
    keyboard=[]
    for key,value in locations_for_chosen_hour:
        keyboard.insert(len(keyboard), [InlineKeyboardButton(key, callback_data=value)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text="Please choose appointment location:", reply_markup=reply_markup)
    
    #Clear appointments_dictionary to avoid issues when user retries
    appointments_dictionary.clear()
    return FIRST

def book_appointment(update,context):
    #read session from context
    session = context.user_data['session']
    query = update.callback_query
    query.answer()
    
    #Recreate URL from the location_choice function
    register_url = 'https://service.berlin.de' + query.data
    r = session.get(register_url)
    booking_url = r.url
    
    #Save booking_url value to context for another function
    #Yes I should have used it earlier, this is the point where I realized what context is used for. LOL
    context.user_data['booking_url'] = booking_url
    query.message.reply_text('Please type your name and surname')

    return THREE

#Function to get user's name and surname and save it to context
def get_user_name(update,context):
    name_and_surname = update.message.text
    context.user_data['name'] = name_and_surname
    
    #Debug MSG
    print(name_and_surname)
    update.message.reply_text('Please enter your e-mail address')
    return FOURTH

#Function to get user's email address and save it to context
def get_user_email(update,context):
    email = update.message.text
    context.user_data['email'] = email
    
    #Debug MSG
    print(email)
    update.message.reply_text('Please enter your phone number')
    return FIFTH

#Function to get user's phone number and save it to context.
def get_user_phone(update,context):
    phone_number = update.message.text
    context.user_data['phone'] = phone_number 
    user_data = context.user_data
    #Debug MSGs
    print(phone_number)
    print(user_data)
    
    #Create a submit button
    keyboard = [
        [
            InlineKeyboardButton('Submit', callback_data='submit'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text='Submit the data!', reply_markup=reply_markup)
    return POST_INFORMATION

def submit_data(update,context):
    #read session from  context
    session = context.user_data['session']
    user_data = context.user_data
    query = update.callback_query
    query.answer()
    #Check if context is working properly
    print(user_data)
    url = user_data['booking_url']
    
    #Data needed for a successful POST
    data = {"familyName": user_data['name'], "email": user_data['email'], "telephone": user_data['phone'], "surveyAccepted": 0, "agbgelesen": 1, "form_validate": 1,}
    r = session.post(url, data)
    
    #Debug MSGs to see if everything went smoothly
    print('SUBMITTED')
    print(r.status_code)
    if r.ok:
        print('It worked?')
    print('\n\nThis is the url that we were redirected to: ' + r.url)
    confirmed = r.url
    
    if confirmed != 'https://service.berlin.de/terminvereinbarung/termin/confirm/':
        query.message.reply_text(text='Something went wrong. Please enter /start and try booking an appointment again.')
    else:
        query.message.reply_text(text='Your appointment was booked successfully. Please check your e-mail to get the appointment number and the rest of the info. Enjoy your visit at Bürgeramt!')

#Needed to allow the bot to work when user types in the /start function without sending any callback data (so, without clicking a button)
#This is taken straight from the example available at telegram bot GitHub
def start_over(update, context):
    """Prompt same text & keyboard as `start` does but not as new message"""
    # Get CallbackQuery from Update
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()
    keyboard = [
        [
            InlineKeyboardButton('Anmelden', callback_data=str(ONE)),
            InlineKeyboardButton('Show a dog', callback_data=str(TWO))
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Instead of sending a new message, edit the message that
    # originated the CallbackQuery. This gives the feeling of an
    # interactive menu.
    query.edit_message_text(text='Hi again' , reply_markup=reply_markup)
    return FIRST

#End (under construction)
def end(update, context):
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over"""
    query = update.callback_query
    query.answer()
    query.edit_message_text(text="See you next time!")
    return ConversationHandler.END

def main():
    updater = Updater('1459753252:AAH7ZpSbBBKEfRqVaAsN1fXYuijgKIGe544', use_context=True)
    dp = updater.dispatcher
    
    #Use ConversationHandler to handle conversation state based on the callback data received
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FIRST: [

                #Callback data needs to be different, pay attention to regex matches as wrong one could redirect to the wrong function

                CallbackQueryHandler(anmelden, pattern='^' + str(ONE) + '$'),
                
                #Regex to match the date
                CallbackQueryHandler(appointment_choice, pattern='^[0-9]* +[A-Za-z]'),
                
                #Callback data from appointment_choice function is exact time in HH:MM format plus URL endpoint, this regex works fine:
                CallbackQueryHandler(location_choice, pattern='^[0-9]{2}:.*'),
                
                #Callback data is the appointment endpoint
                CallbackQueryHandler(book_appointment, pattern='^/terminvereinbarung/.*'),
            ],
            SECOND: [
                CallbackQueryHandler(start_over, pattern='^' + str(ONE) + '$'),
                CallbackQueryHandler(end, pattern='^' + str(TWO) + '$')
            ],
            THIRD:
            [
                MessageHandler(Filters.text, get_user_name),
            ],
            FOURTH:
            [
                MessageHandler(Filters.text, get_user_email),
            ],
            FIFTH:
            [
                MessageHandler(Filters.text, get_user_phone),
            ],
            POST_INFORMATION:
            [
                #Callback data == 'submit'
                CallbackQueryHandler(submit_data, pattern='^submit$')
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    dp.add_handler(conv_handler)
    updater.start_polling()

if __name__ == '__main__':
    main()

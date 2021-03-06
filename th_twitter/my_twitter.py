# coding: utf-8
import arrow

# Twitter lib
from twython import Twython

# django classes
from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils.log import getLogger
from django.utils.translation import ugettext as _
from django.core.cache import caches

# django_th classes
from django_th.services.services import ServicesMgr
from django_th.models import UserService, ServicesActivated
from django_th.html_entities import HtmlEntities

from th_twitter.models import Twitter
"""
    handle process with twitter
    put the following in settings.py

    TH_TWITTER = {
        'consumer_key': 'abcdefghijklmnopqrstuvwxyz',
        'consumer_secret': 'abcdefghijklmnopqrstuvwxyz',
    }

"""

logger = getLogger('django_th.trigger_happy')
cache = caches['th_twitter']


class ServiceTwitter(ServicesMgr):

    def __init__(self, token=None):
        self.consumer_key = settings.TH_TWITTER['consumer_key']
        self.consumer_secret = settings.TH_TWITTER['consumer_secret']
        if token is not None:
            token_key, token_secret = token.split('#TH#')
            self.twitter_api = Twython(self.consumer_key, self.consumer_secret,
                                       token_key, token_secret)

    def read_data(self, token, trigger_id, date_triggered):
        """
            get the data from the service

            :param trigger_id: trigger ID to process
            :param date_triggered: the date of the last trigger
            :type trigger_id: int
            :type date_triggered: datetime
            :return: list of data found from the date_triggered filter -
            data has to return {'content': 'a text',
            'link': 'a valid url to the ressource'}
            :rtype: list
        """
        twitter_url = 'https://www.twitter.com/{}/status/{}'
        now = arrow.utcnow().to(settings.TIME_ZONE)
        my_tweets = []
        search = {}
        since_id = None

        def _get_tweets(twitter_obj, search):
            """
                get the tweets from twitter and return the filters to use :
                search and count

                :param twitter_obj: from Twitter model
                :param search: filter used for twython.search() or
                twython.get_user_timeline())
                :type twitter_obj: Object
                :type search: dict
                :return: count that limit the quantity of tweet to retrieve,
                the filter named search, the tweets
                :rtype: list
            """

            """
                explanations about statuses :
                when we want to track the tweet of a screen
                statuses contain all of them
                when we want to track all the tweet matching a tag
                statuses contain statuses + metadata array
                this is why we need to do
                statuses = statuses['statuses']
                to be able to handle the result as for screen_name
            """

            # get the tweets for a given tag
            # https://dev.twitter.com/docs/api/1.1/get/search/tweets
            statuses = ''
            count = 100
            if twitter_obj.tag != '':
                count = 100
                search['count'] = count
                search['q'] = twitter_obj.tag
                search['result_type'] = 'recent'
                # do a search
                statuses = self.twitter_api.search(**search)
                # just return the content of te statuses array
                statuses = statuses['statuses']

            # get the tweets from a given user
            # https://dev.twitter.com/docs/api/1.1/get/statuses/user_timeline
            elif twitter_obj.screen != '':
                count = 200
                search['count'] = count
                search['screen_name'] = twitter_obj.screen
                # call the user timeline and get his tweet
                statuses = self.twitter_api.get_user_timeline(**search)

            return count, search, statuses

        if token is not None:
            twitter_obj = Twitter.objects.get(trigger_id=trigger_id)

            # https://dev.twitter.com/rest/public/timelines
            if twitter_obj.since_id is not None and twitter_obj.since_id > 0:
                since_id = twitter_obj.since_id
                search = {'since_id': twitter_obj.since_id}

            # first request to Twitter
            count, search, statuses = _get_tweets(twitter_obj, search)

            if len(statuses) > 0:
                newest = None
                for status in statuses:
                    if newest is None:
                        newest = True
                        # first query ; get the max id
                        search['max_id'] = max_id = status['id']

                since_id = search['since_id'] = statuses[-1]['id'] - 1

                count, search, statuses = _get_tweets(twitter_obj, search)

                newest = None
                if len(statuses) > 0:
                    my_tweets = []
                    for s in statuses:
                        if newest is None:
                            newest = True
                            max_id = s['id'] - 1
                        screen_name = s['user']['screen_name']
                        # get the text of the tweet + url to this one
                        url = twitter_url.format(screen_name,
                                                 s['id_str'])
                        title = _('Tweet from @{}'.format(screen_name))
                        # Wed Aug 29 17:12:58 +0000 2012
                        my_date = arrow.get(s['created_at'],
                                            'ddd MMM DD HH:mm:ss Z YYYY')
                        published = arrow.get(my_date).to(settings.TIME_ZONE)
                        if date_triggered is not None and \
                           published is not None and \
                           now >= published and \
                           published >= date_triggered:
                            my_tweets.append({'title': title,
                                              'content': s['text'],
                                              'link': url,
                                              'my_date': my_date})
                    cache.set('th_twitter_' + str(trigger_id), my_tweets)
                    Twitter.objects.filter(trigger_id=trigger_id).update(
                        since_id=since_id,
                        max_id=max_id,
                        count=count)
        return my_tweets

    def process_data(self, trigger_id):
        """
            get the data from the cache
            :param trigger_id: trigger ID from which to save data
            :type trigger_id: int
        """
        return cache.get('th_twitter_' + str(trigger_id))

    def save_data(self, token, trigger_id, **data):
        """
            let's save the data

            :param trigger_id: trigger ID from which to save data
            :param **data: the data to check to be used and save
            :type trigger_id: int
            :type **data:  dict
            :return: the status of the save statement
            :rtype: boolean
        """
        status = False
        tags = []
        content = ''
        if token and 'link' in data and data['link'] is not None and \
           len(data['link']) > 0:
            # get the Twitter data of this trigger
            trigger = Twitter.objects.get(trigger_id=trigger_id)

            link = data['link']

            if trigger.tag:
                # is there several tag ?
                if ',' in trigger.tag:
                    for tag in trigger.tag.split(','):
                        tags.append('#' + tag.strip())
                # no
                else:
                    tags.append('#' + trigger.tag)

            if 'title' in data and data['title'] is not None and \
               len(data['title']) > 0:
                title = data['title']
                # decode html entities if any
                title = HtmlEntities(title).html_entity_decode

                content = str("{title} {link}").format(title=title, link=link)

            # TODO : need to check the size of the content and tags to add
            if len(tags) > 0:
                content += ' ' + str(','.join(tags))

            try:
                self.twitter_api.update_status(status=content)
                status = True
            except Exception as inst:
                logger.critical("Twitter ERR {}".format(inst))
                status = False
        return status

    def auth(self, request):
        """
        build the request to access to the Twitter
        website with all its required parms
        :param request: makes the url to call Twitter + the callback url
        :return: go to the Twitter website to ask to the user
        to allow the access of TriggerHappy
        """
        callback_url = 'http://%s%s' % (
            request.get_host(), reverse('twitter_callback'))

        twitter = Twython(self.consumer_key, self.consumer_secret)

        req_token = twitter.get_authentication_tokens(
            callback_url=callback_url)
        request.session['oauth_token'] = req_token['oauth_token']
        request.session['oauth_token_secret'] = req_token['oauth_token_secret']

        return req_token['auth_url']

    def callback(self, request):
        """
            Called from the Service when the user accept to activate it
        """
        try:
            # retrieve the token from the session
            access_token = self.get_access_token(
                request.session['oauth_token'],
                request.session['oauth_token_secret'],
                request.GET.get('oauth_verifier', '')
            )
            # make the token
            token = access_token['oauth_token'] + '#TH#'\
                + access_token['oauth_token_secret']
            # finally we save the user auth token
            UserService.objects.filter(
                user=request.user,
                name=ServicesActivated.objects.get(name='ServiceTwitter')
            ).update(token=token)

        except KeyError:
            return '/'

        return 'twitter/callback.html'

    def get_access_token(
        self, oauth_token, oauth_token_secret, oauth_verifier
    ):
        """
        :param oauth_token: oauth_token retrieve by the API Twython
        get_authentication_tokens()
        :param oauth_token_secret: oauth_token_secret retrieve by the
        API Twython get_authentication_tokens()
        :param oauth_verifier: oauth_verifier retrieve from Twitter
        :type oauth_token: string
        :type oauth_token_secret: string
        :type oauth_verifier: string
        :return: access_token
        :rtype: dict
        """
        twitter = Twython(self.consumer_key,
                          self.consumer_secret,
                          oauth_token,
                          oauth_token_secret)
        access_token = twitter.get_authorized_tokens(oauth_verifier)
        return access_token

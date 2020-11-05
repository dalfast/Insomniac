from abc import ABC
import random
from enum import unique, Enum

from insomniac.safely_runner import run_safely
from insomniac.utils import print_timeless, COLOR_FAIL, COLOR_ENDC, COLOR_WARNING, get_value, COLOR_BOLD


class ActionRunnersManager(object):
    action_runners = {}

    def __init__(self):
        for clazz in get_core_action_runners_classes():
            instance = clazz()
            self.action_runners[instance.ACTION_ID] = instance

    def get_actions_args(self):
        actions_args = {}

        for key, action_runner in self.action_runners.items():
            for arg, info in action_runner.ACTION_ARGS.items():
                actions_args.update({arg: info})

        return actions_args

    def select_action_runner(self, args):
        selected_action_runners = []

        for action_runner in self.action_runners.values():
            if action_runner.is_action_selected(args):
                selected_action_runners.append(action_runner)

        if len(selected_action_runners) == 0:
            print_timeless(COLOR_FAIL + "You have to specify one of the actions: --interact, --unfollow, "
                                        "--unfollow-non-followers, --unfollow-any, --remove-mass-followers" + COLOR_ENDC)
            return None

        if len(selected_action_runners) > 1:
            print_timeless(COLOR_FAIL + "Running Insomniac with two or more actions is not supported yet." + COLOR_ENDC)
            return None

        print_timeless(COLOR_WARNING +
                       "Running Insomniac with {0} action.".format(selected_action_runners[0].ACTION_ID) +
                       COLOR_ENDC)

        return selected_action_runners[0]


@unique
class ActionState(Enum):
    PRE_RUN = 0
    RUNNING = 1
    DONE = 2
    SOURCE_LIMIT_REACHED = 3
    SESSION_LIMIT_REACHED = 4


class ActionStatus(object):
    def __init__(self, state):
        self.state = state
        self.limit_state = None

    def set(self, state):
        self.state = state

    def get(self):
        return self.state

    def set_limit(self, limit_state):
        self.limit_state = limit_state

    def get_limit(self):
        return self.limit_state


class ActionsRunner(object):
    """An interface for actions-runner object"""

    ACTION_ID = "OVERRIDE"
    ACTION_ARGS = {"OVERRIDE": "OVERRIDE"}

    action_status = None

    def is_action_selected(self, args):
        raise NotImplementedError()

    def set_params(self, args):
        raise NotImplementedError()

    def run(self, device_wrapper, storage, session_state, on_action, is_limit_reached, is_passed_filters=None):
        raise NotImplementedError()


class CoreActionsRunner(ActionsRunner, ABC):
    """An interface for extra-actions-runner object"""


class InteractBySourceActionRunner(CoreActionsRunner):
    ACTION_ID = "interact"
    ACTION_ARGS = {
        "likes_count": {
            "help": "number of likes for each interacted user, 2 by default. "
                    "It can be a number (e.g. 2) or a range (e.g. 2-4)",
            'metavar': '2-4',
            "default": '2'
        },
        "follow_percentage": {
            "help": "follow given percentage of interacted users, 0 by default",
            "metavar": '50',
            "default": '0'
        },
        "interact": {
            "nargs": '+',
            "help": 'list of hashtags and usernames. Usernames should start with \"@\" symbol. '
                    'The script will interact with hashtags\' posts likers and with users\' followers',
            "default": [],
            "metavar": ('hashtag', '@username')
        },
        "interaction_users_amount": {
            "help": 'add this argument to select an amount of users from the interact-list '
                    '(users are randomized). It can be a number (e.g. 4) or a range (e.g. 3-8)',
            'metavar': '3-8'
        }
    }

    likes_count = 2
    follow_percentage = 0
    interact = []

    def is_action_selected(self, args):
        return args.interact is not None and len(args.interact) > 0

    def set_params(self, args):
        if args.likes_count is not None:
            self.likes_count = args.likes_count

        if args.interact is not None:
            self.interact = args.interact.copy()
            self.interact = [source if source[0] == '@' else ('#' + source) for source in self.interact]

        if args.follow_percentage is not None:
            self.follow_percentage = int(args.follow_percentage)

        if args.interaction_users_amount is not None:
            if len(self.interact) > 0:
                users_amount = get_value(args.interaction_users_amount, "Interaction user amount {}", 100)

                if users_amount >= len(self.interact):
                    print("interaction-users-amount parameter is equal or higher then the users-interact list. "
                          "Choosing all list for interaction.")
                else:
                    amount_to_remove = len(self.interact) - users_amount
                    for i in range(0, amount_to_remove):
                        self.interact.remove(random.choice(self.interact))

    def run(self, device_wrapper, storage, session_state, on_action, is_limit_reached, is_passed_filters=None):
        from insomniac.action_handle_blogger import handle_blogger

        random.shuffle(self.interact)

        for source in self.interact:
            self.action_status = ActionStatus(ActionState.PRE_RUN)

            likes_count = get_value(self.likes_count, "Likes count: {}", 2)
            if likes_count > 12:
                print(COLOR_FAIL + "Max number of likes per user is 12" + COLOR_ENDC)
                likes_count = 12

            if source[0] == '@':
                is_myself = source[1:] == session_state.my_username
                print_timeless("")
                print(COLOR_BOLD + "Handle " + source + (is_myself and " (it\'s you)" or "") + COLOR_ENDC)
            elif source[0] == '#':
                print_timeless("")
                print(COLOR_BOLD + "Handle " + source + COLOR_ENDC)

            @run_safely(device_wrapper=device_wrapper)
            def job():
                self.action_status.set(ActionState.RUNNING)
                if source[0] == '@':
                    handle_blogger(device_wrapper.get(),
                                   source[1:],  # drop "@"
                                   session_state,
                                   likes_count,
                                   self.follow_percentage,
                                   storage,
                                   on_action,
                                   is_limit_reached,
                                   is_passed_filters,
                                   self.action_status)
                # elif source[0] == '#':
                #     handle_hashtag(device_wrapper.get(),
                #                    source[1:],  # drop "#"
                #                    session_state,
                #                    self.likes_count,
                #                    self.follow_percentage,
                #                    storage,
                #                    on_action,
                #                    is_limit_reached,
                #                    is_passed_filters,
                #                    self.action_status)

                self.action_status.set(ActionState.DONE)

            while not self.action_status.get() == ActionState.DONE:
                job()
                if self.action_status.get_limit() == ActionState.SOURCE_LIMIT_REACHED or \
                   self.action_status.get_limit() == ActionState.SESSION_LIMIT_REACHED:
                    break

            if self.action_status.get_limit() == ActionState.SOURCE_LIMIT_REACHED:
                continue

            if self.action_status.get_limit() == ActionState.SESSION_LIMIT_REACHED:
                break


class UnfollowActionRunner(CoreActionsRunner):
    ACTION_ID = "unfollow"
    ACTION_ARGS = {
        "unfollow": {
            "help": 'unfollow at most given number of users. Only users followed by this script will '
                    'be unfollowed. The order is from oldest to newest followings. '
                    'It can be a number (e.g. 100) or a range (e.g. 100-200)',
            "metavar": '100-200'
        },
        "min_following": {
            "help": 'minimum amount of followings, after reaching this amount unfollow stops',
            "metavar": '100',
            "default": "0"
        }
    }

    unfollow = 0
    min_following = 0

    def is_action_selected(self, args):
        return args.unfollow is not None

    def set_params(self, args):
        if args.unfollow is not None:
            self.unfollow = get_value(args.unfollow, "Unfollow {}", 100)

        if args.min_following is not None:
            self.min_following = int(args.min_following)

    def run(self, device_wrapper, storage, session_state, on_action, is_limit_reached, is_passed_filters=None):
        pass


class UnfollowNonFollowersActionRunner(CoreActionsRunner):
    ACTION_ID = "unfollow_non_followers"
    ACTION_ARGS = {
        "unfollow_non_followers": {
            "help": 'unfollow at most given number of users, that don\'t follow you back. Only users followed '
                    'by this script will be unfollowed. The order is from oldest to newest followings. '
                    'It can be a number (e.g. 100) or a range (e.g. 100-200)',
            "metavar": '100-200'
        },
        "min_following": {
            "help": 'minimum amount of followings, after reaching this amount unfollow stops',
            "metavar": '100',
            "default": "0"
        }
    }

    unfollow_non_followers = 0
    min_following = 0

    def is_action_selected(self, args):
        return args.unfollow_non_followers is not None

    def set_params(self, args):
        if args.unfollow_non_followers is not None:
            self.unfollow_non_followers = get_value(args.unfollow_non_followers, "Unfollow {} non followers", 100)

        if args.min_following is not None:
            self.min_following = int(args.min_following)

    def run(self, device_wrapper, storage, session_state, on_action, is_limit_reached, is_passed_filters=None):
        pass


class UnfollowAnyActionRunner(CoreActionsRunner):
    ACTION_ID = "unfollow_any"
    ACTION_ARGS = {
        "unfollow_any": {
            "help": 'unfollow at most given number of users. The order is from oldest to newest followings. '
                    'It can be a number (e.g. 100) or a range (e.g. 100-200)',
            "metavar": '100-200'
        },
        "min_following": {
            "help": 'minimum amount of followings, after reaching this amount unfollow stops',
            "metavar": '100',
            "default": "0"
        }
    }

    unfollow_any = 0
    min_following = 0

    def is_action_selected(self, args):
        return args.unfollow_any is not None

    def set_params(self, args):
        if args.unfollow_any is not None:
            self.unfollow_any = get_value(args.unfollow_any, "Unfollow {} any", 100)

        if args.min_following is not None:
            self.min_following = int(args.min_following)

    def run(self, device_wrapper, storage, session_state, on_action, is_limit_reached, is_passed_filters=None):
        pass


def get_core_action_runners_classes():
    return CoreActionsRunner.__subclasses__()
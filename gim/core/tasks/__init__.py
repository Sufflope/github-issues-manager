class JobRegistry(set):

    @property
    def classes(self):
        return self

JobRegistry = JobRegistry()


from .cleanup import *
from .comment import *
from .commit import *
from .event import *
from .general import *
from .githubuser import *
from .issue import *
from .label import *
from .milestone import *
from .repository import *
from .tokens import *
from .project import *

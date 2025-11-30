import inspect
from strands import Agent

print(inspect.signature(Agent.__init__))
print(inspect.signature(Agent.__call__))

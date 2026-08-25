from typing import Protocol
class EnvironmentBindingAdapter(Protocol):
    def resolve(self,requirements:dict)->list[dict]: ...

class NullEnvironmentBindingAdapter:
    def resolve(self,requirements):
        return []

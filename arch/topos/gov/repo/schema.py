# arch.topos.gov.repo.schema
## @lineage: gov.state.repo.schema
## @lineage: gov.state.system.repo.schema
## @lineage: gov.repo.commit
from dataclasses import dataclass, asdict, field
from typing import Dict
import json

@dataclass
class RepoCommit:
    """
    @role: local node lineage inscription
    @commit: (parent_anchor_id, parent_commit_id)
    """

    ## current alignment event (perspective instance)
    anchor_id: str

    ## reference anchor defining lineage selection context
    parent_anchor_id: str

    ## resolved parent state under parent_anchor_id
    parent_commit_id: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(',', ':'))


@dataclass
class AnchorCommit:
    """
    @role: global boundary + alignment surface
    @anchor_commit: (parent_anchor_id, parent_commit_id) + alignment partition (repos / cached_states)
    """

    ## current alignment event identifier
    anchor_id: str

    ## previous anchor (lineage reference frame)
    parent_anchor_id: str

    ## self parent resolved under parent_anchor_id
    parent_commit_id: str

    ## repo_name -> commit_id (result of current alignment)
    repos: Dict[str, str] = field(default_factory=dict)

    ## repo_name -> last known commit_id (not aligned in this anchor)
    cached_states: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(',', ':'))
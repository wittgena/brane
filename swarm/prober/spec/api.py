# swarm.prober.spec.api
## @lineage: hub.nexus.system.api
## @lineage: scripts.xyz.xor.code.tracking.hands.api
## @lineage: foldbox.spec.prober.api.spec

PROBE_SPEC = [
    {
        "name": "Ψ₀:genesis",
        "method": "POST",
        "path": "/api/conversations",
        "extract": {"conversation_id": ["id", "conversation_id"]} 
    },
    {
        "name": "Ψᵢ:injection",
        "method": "POST",
        "path": "/api/conversations/{conversation_id}/events"
    },
    {
        "name": "Ψ:activation",
        "method": "POST",
        "path": "/api/conversations/{conversation_id}/run"
    },
    {
        "name": "Φ′:observation",
        "method": "GET",
        "path": "/api/conversations/{conversation_id}/events/search"
    }
]
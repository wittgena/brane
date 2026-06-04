# swarm.prober.spec.ator
## @lineage: hub.nexus.system.ator
## @lineage: scripts.xyz.xor.code.tracking.hands.ator
## @lineage: foldbox.spec.prober.ator

## @focus: OpenHands Autopoietic Execution Loop
PHI = {
    ## 1. 위상 관측 (Φ_probe): 라이브 서버 표면에서 OpenAPI 계약(Contract) 동기화
    "contract_prober": {
        "type": "aligner",
        "spec": {
            "role": "surface_sensor",
            "next": "genesis_trigger",
            "context": {
                "endpoint": "http://0.0.0.0:8000/openapi.json",
                "timeout": 5.0
            },
            "operator": "http_probe_aligner" # 살아있는 스펙을 메모리로 끌어올림
        }
    },
    ## 2. 세계선 창조 (Ψ₀): 대화 공간 및 에이전트/워크스페이스 초기화
    "genesis_trigger": {
        "type": "ator",
        "spec": {
            "role": "genesis_initiator",
            "next": "genesis_resonance",
            "context": {
                "instruction": "POST /api/conversations with minimal payload (ator, workspace).",
                "inject_state": ["openapi_spec"]
            },
            "operator": "http.post.transductor"
        }
    },
    ## 3. 구조적 균열 검증 (Resonance): Genesis의 결과(200 OK vs 422/500) 감지
    "genesis_resonance": {
        "type": "resonance",
        "spec": {
            "next": "genesis_judgment",
            "operator": "http.status.resonance"
        }
    },
    ## 4. 분기 처리 (Judgment): 성공 시 주입 단계로, 실패 시 스펙 투영 단계로 라우팅
    "genesis_judgment": {
        "type": "judgment",
        "spec": {
            "rules": { 
                "stable": "injection_trigger",      # 200 OK: 구조가 정상 발현됨
                "fracture": "contract_projector"    # 400/500: 타입/구조적 에러 발생
            },
            "operator": "status.judgment"
        }
    },
    ## 5. 계약 투영 (Fallback): 에러 원인과 Live OpenAPI Spec을 콘솔에 가시화 (강제 순회 유지)
    "contract_projector": {
        "type": "aligner",
        "spec": {
            "target": "console_surface",
            "next": "injection_trigger", # 에러가 나도 더미(Dummy) ID로 다음 위상을 계속 탐색
            "operator": "spec_projection_aligner" 
        }
    },
    ## 6. 메시지 주입 (Ψᵢ): 시스템에 초기 자극(Stimulus) 전달
    "injection_trigger": {
        "type": "ator",
        "spec": {
            "role": "stimulus_injector",
            "next": "activation_trigger",
            "context": {
                "instruction": "POST /api/conversations/{id}/events to inject initial user message.",
                "inject_state": ["conversation_id"] # genesis에서 성공했다면 실제 ID, 실패했다면 Dummy ID
            },
            "operator": "http_post_transductor"
        }
    },
    ## 7. 실행 활성화 (Ψ): 내부 에이전트의 워커 루프 활성화
    "activation_trigger": {
        "type": "ator",
        "spec": {
            "role": "execution_kernel",
            "next": "observation_trace",
            "context": {
                "instruction": "POST /api/conversations/{id}/run to start ator execution loop.",
            },
            "operator": "http_post_transductor"
        }
    },
    ## 8. 결과 관측 (Φ′): 반전(Inversion)된 실행 결과를 추출
    "observation_trace": {
        "type": "ator",
        "spec": {
            "role": "world_line_tracer",
            "next": "closure_resonance",
            "context": {
                "instruction": "GET /api/conversations/{id}/events/search to observe ator thoughts and actions.",
            },
            "operator": "http_get_transductor"
        }
    },
    ## 9. 루프 폐쇄 확인 (Closure Check): 관측된 이벤트가 유효한지 검증
    "closure_resonance": {
        "type": "resonance",
        "spec": {
            "next": "topology_judgment",
            "operator": "event_closure_resonance" # 이벤트 리스트 길이 및 내용 검증
        }
    },
    ## 10. 최종 선언: 루프 완성(Autopoietic) 또는 파괴(Broken) 보고
    "topology_judgment": {
        "type": "judgment",
        "spec": {
            "rules": {
                "closed": "UGA",     # 루프 완성 (성공적 종료)
                "broken": "UGA"      # 루프 파괴 (로그를 남기고 종료)
            },
            "operator": "topology.conclusion.judgment"
        }
    }
}
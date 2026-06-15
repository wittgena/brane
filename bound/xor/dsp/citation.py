# bound.xor.dsp.citation
## @lineage: bound.channel.bridge.dsp.citation
## @lineage: channel.bridge.dsp.citation
## @lineage: meta.xor.manifold.citation
from typing import Any, Optional
import pydantic
from bound.xor.basetype import Type

from arch.contract.exp.frag import exp
from arch.xor.manifold.sign.field import InputField, OutputField

from watcher.plane.emitter import get_emitter

log = get_emitter("manifold.citation", phase="parsing", boundary="manifold")

@exp(version="1.0.1")
class Citations(Type):
    class Citation(Type):
        type: str = "char_location"
        cited_text: str
        document_index: int
        document_title: str | None = None
        start_char_index: int
        end_char_index: int
        supported_text: str | None = None

        def format(self) -> dict[str, Any]:
            citation_dict = {
                "type": self.type,
                "cited_text": self.cited_text,
                "document_index": self.document_index,
                "start_char_index": self.start_char_index,
                "end_char_index": self.end_char_index,
            }

            if self.document_title:
                citation_dict["document_title"] = self.document_title
            if self.supported_text:
                citation_dict["supported_text"] = self.supported_text

            return citation_dict

    citations: list[Citation]

    @classmethod
    def from_dict_list(cls, citations_dicts: list[dict[str, Any]]) -> "Citations":
        citations = [cls.Citation(**item) for item in citations_dicts]
        return cls(citations=citations)

    @classmethod
    def description(cls) -> str:
        return (
            "Citations with quoted text and source references. "
            "Include the exact text being cited and information about its source."
        )

    def format(self) -> list[dict[str, Any]]:
        return [citation.format() for citation in self.citations]

    @pydantic.model_validator(mode="before")
    @classmethod
    def validate_input(cls, data: Any):
        if isinstance(data, cls):
            return data

        ## Handle case where data is a list of dicts with citation info
        if isinstance(data, list) and all(isinstance(item, dict) and "cited_text" in item for item in data):
            log.trace("Citation list structured", input_type="list_of_dicts", count=len(data))
            return {"citations": [cls.Citation(**item) for item in data]}

        ## Handle case where data is a dict
        elif isinstance(data, dict):
            if "citations" in data:
                citations_data = data["citations"]
                if isinstance(citations_data, list):
                    log.trace("Citation dict structured", input_type="dict_with_citations_key", count=len(citations_data))
                    return {
                        "citations": [
                            cls.Citation(**item) if isinstance(item, dict) else item for item in citations_data
                        ]
                    }
            elif "cited_text" in data:
                log.trace("Citation dict structured", input_type="single_citation_dict", count=1)
                return {"citations": [cls.Citation(**data)]}

        ## 파싱 실패 시, 로깅이 아닌 도메인 에러 이벤트(ERROR)로 기록
        log.error("Invalid citation data received", invalid_data_type=type(data).__name__, raw_data=str(data))
        raise ValueError(f"Received invalid value for `Citations`: {data}")

    def __iter__(self):
        return iter(self.citations)

    def __len__(self):
        return len(self.citations)

    def __getitem__(self, index):
        return self.citations[index]

    @classmethod
    def adapt_to_native_lm_feature(cls, signature, field_name, lm, lm_kwargs) -> bool:
        if lm.model.startswith("anthropic/"):
            ## 비즈니스 로직상의 우회/폴백은 signal로 방출하여 추적망에 상태 변경을 알림
            log.signal(
                "Citation adaptation skipped", 
                reason="unsupported_provider", 
                model=lm.model, 
                field=field_name
            )
            return signature.delete(field_name)
        
        log.trace("Citation adapted to native LM", model=lm.model, field=field_name)
        return signature

    @classmethod
    def is_streamable(cls) -> bool:
        return True

    @classmethod
    def parse_stream_chunk(cls, chunk) -> Optional["Citations"]:
        try:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "provider_specific_fields") and delta.provider_specific_fields:
                    citation_data = delta.provider_specific_fields.get("citation")
                    if citation_data:
                        ## 스트림 중 데이터 도달 이벤트를 trace로 기록 (볼륨이 크므로 debug보다 낮게)
                        log.trace("Streamed citation chunk parsed", doc_index=citation_data.get("document_index"))
                        return cls.from_dict_list([citation_data])
        except Exception as e:
            ## 스트림 파싱 에러는 흐름을 끊지 않지만 내부 plane에는 남겨둠
            log.warning("Stream chunk parsing failed", exc_info=True, chunk_data=str(chunk))
        return None

    @classmethod
    def parse_lm_response(cls, response: str | dict[str, Any]) -> Optional["Citations"]:
        if isinstance(response, dict):
            if "citations" in response:
                citations_data = response["citations"]
                if isinstance(citations_data, list):
                    ## 최종 결과 도출 이벤트를 info로 기록하여 사이클 종료 확인
                    log.info("LM response citations parsed successfully", count=len(citations_data))
                    return cls.from_dict_list(citations_data)

        log.debug("No citations found in LM response", response_type=type(response).__name__)
        return None
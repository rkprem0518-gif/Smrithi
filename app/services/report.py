"""ScoreResult -> the report JSON the Report page renders, with plain-language text (en/hi)."""

from __future__ import annotations

from typing import Any

from app.config_loader import animal_hindi_names
from app.scoring.outcome import INVALID, NORMAL, REFER, UNCERTAIN
from app.scoring.types import ScoringConfig

OUTCOME_LABEL = {
    NORMAL: {"en": "Normal", "hi": "सामान्य"},
    UNCERTAIN: {"en": "Uncertain - retest", "hi": "अस्पष्ट - दोबारा जाँच करें"},
    REFER: {"en": "Refer to clinician", "hi": "डॉक्टर से मिलें"},
    INVALID: {"en": "Invalid call", "hi": "अमान्य कॉल"},
}

NEXT_STEP = {
    NORMAL: {
        "en": "No memory concerns showed up on this short check. This is not a diagnosis. If you or your "
              "family notice changes in memory or daily activities, talk to a doctor. The check can be "
              "repeated in 6-12 months.",
        "hi": "इस छोटी जाँच में याददाश्त से जुड़ी कोई चिंता नहीं दिखी। यह कोई निदान नहीं है। अगर आपको या "
              "परिवार को याददाश्त या रोज़ के कामों में बदलाव दिखे, तो डॉक्टर से बात करें। यह जाँच 6-12 "
              "महीने बाद दोबारा की जा सकती है।",
    },
    UNCERTAIN: {
        "en": "The result is unclear. A trained reviewer will look at this call. We suggest repeating the "
              "check in a few weeks, in a quiet place. If you are worried, talk to a doctor.",
        "hi": "नतीजा साफ़ नहीं है। एक प्रशिक्षित व्यक्ति इस कॉल को देखेगा। कुछ हफ़्तों बाद, शांत जगह पर "
              "जाँच दोबारा करें। अगर चिंता हो, तो डॉक्टर से बात करें।",
    },
    REFER: {
        "en": "Some answers suggest it is worth seeing a doctor (a general physician, neurologist or memory "
              "clinic) for a proper check. This is not a diagnosis: hearing, mood, sleep, medicines and "
              "vitamin levels can all affect memory, and many causes are treatable. A trained reviewer "
              "will also look at this call.",
        "hi": "कुछ जवाबों से लगता है कि किसी डॉक्टर (सामान्य डॉक्टर, न्यूरोलॉजिस्ट या मेमोरी क्लिनिक) से "
              "ठीक से जाँच करवाना अच्छा रहेगा। यह कोई निदान नहीं है: सुनने की दिक्कत, मन की स्थिति, नींद, "
              "दवाइयाँ और विटामिन भी याददाश्त पर असर डालते हैं, और कई कारणों का इलाज हो सकता है। एक "
              "प्रशिक्षित व्यक्ति भी इस कॉल को देखेगा।",
    },
    INVALID: {
        "en": "We could not get a reliable result from this call. Please try again on a clearer line, in a "
              "quiet place, with the person answering alone. If hearing was the problem, an in-person "
              "check (including a hearing check) is better than a phone call.",
        "hi": "इस कॉल से भरोसेमंद नतीजा नहीं मिल सका। कृपया साफ़ लाइन पर, शांत जगह में, और बिना किसी की "
              "मदद के दोबारा कोशिश करें। अगर सुनने में दिक्कत थी, तो फ़ोन के बजाय आमने-सामने जाँच (सुनने "
              "की जाँच समेत) बेहतर है।",
    },
}

INVALID_REASONS = {
    "hearing_check_failed": {
        "en": "the hearing/line check failed (fewer than 2 of 3 number strings repeated)",
        "hi": "सुनने/लाइन की जाँच सफल नहीं हुई (3 में से 2 से कम अंक दोहराए गए)",
    },
    "ended_before_delayed_recall": {
        "en": "the call ended before the last memory task",
        "hi": "आख़िरी याददाश्त वाले काम से पहले कॉल ख़त्म हो गई",
    },
    "too_many_empty_answers": {
        "en": "more than 30% of answers were empty or could not be understood",
        "hi": "30% से ज़्यादा जवाब ख़ाली थे या समझ नहीं आए",
    },
    "helper_present": {
        "en": "the person said someone was helping them answer",
        "hi": "व्यक्ति ने बताया कि कोई जवाब देने में मदद कर रहा था",
    },
    "stopped_distress": {
        "en": "the call was stopped because the person seemed upset",
        "hi": "व्यक्ति परेशान लगे, इसलिए कॉल रोक दी गई",
    },
}


def build_report(result: dict[str, Any], cfg: ScoringConfig, *, word_form: str, language: str,
                 helpline_text: str = "", call_time: str | None = None) -> dict[str, Any]:
    outcome = result["outcome"]
    learning, recall = result["learning"], result["delayed_recall"]
    fluency, orient = result["fluency"], result["orientation"]
    return {
        "outcome": outcome,
        "outcome_label": OUTCOME_LABEL[outcome],
        "rule_fired": result["rule_fired"],
        "band": result["band"],
        "band_source": result["band_source"],
        "schooling_years": result["schooling_years"],
        "domains": {
            "word_learning": {
                "total": learning["total"], "max": learning["max"], "trials": learning["trials"],
                "intrusions": learning["intrusions"],
            },
            "delayed_recall": {
                "score": recall["score"], "max": recall["max"], "words": recall["words"],
                "intrusions": recall["intrusions"],
            },
            "animal_naming": {
                "count": fluency["count"], "words": fluency["words"],
                "non_animals": fluency["non_animals"], "repeats": fluency["repeats"],
                "experimental_timing": fluency["experimental_timing"],
                "timing_source": fluency["timing_source"],
            },
            "orientation": {
                "score": orient["score"], "max": orient["max"], "items": orient["items"],
                "answers": orient["answers"], "expected": orient["expected"],
                "place_verified": orient["place_verified"],
            },
        },
        "hearing": {"correct": result["hearing"]["correct"], "max": result["hearing"]["max"],
                    "items": result["hearing"]["items"]},
        "word_list": [{"id": w.id, "hi": w.hi, "en": w.en} for w in cfg.forms[word_form]],
        "animal_names": {w: animal_hindi_names().get(w, w) for w in fluency["words"]},
        "word_form": word_form,
        "language": language,
        "call_time": call_time,
        "helper_present": result["helper_present"],
        "consent_call": result["consent_call"],
        "invalid_reasons": result["invalid_reasons"],
        "invalid_reason_text": [INVALID_REASONS[r] for r in result["invalid_reasons"] if r in INVALID_REASONS],
        "empty_answers": result["empty_answers"],
        "next_step_text": NEXT_STEP[outcome],
        "helpline_text": helpline_text or None,
        "speech_markers": result["speech_markers"],
        "not_a_diagnosis": True,
        "pilot_notice": {
            "en": "Smriti is a pilot. It is not a validated test and it never diagnoses. Cutoffs are placeholders.",
            "hi": "स्मृति एक पायलट है। यह मान्य परीक्षण नहीं है और कभी निदान नहीं करता।",
        },
        "scorer_version": result["scorer_version"],
    }

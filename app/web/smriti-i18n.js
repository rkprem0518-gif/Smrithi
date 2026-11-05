/* Smriti screen language: English, हिंदी, ಕನ್ನಡ. The English text is the key, so a missing translation shows English.
   The elder's app is fully translated; the family and care-team apps translate menus and the main labels.
   Hindi and Kannada lines should be checked by a native speaker before real use. */
"use strict";

const UI_LANGS = { en: "English", hi: "हिंदी", kn: "ಕನ್ನಡ" };
// Each call language in its own script, so an elder can find theirs.
const NATIVE = { en: "English", hi: "हिंदी", kn: "ಕನ್ನಡ", ta: "தமிழ்", te: "తెలుగు", ml: "മലയാളം", mr: "मराठी",
  bn: "বাংলা", gu: "ગુજરાતી", pa: "ਪੰਜਾਬੀ", od: "ଓଡ଼ିଆ" };
let UI_LANG = "en";

const STR = {
  hi: {
    // menus and app names
    "Today": "आज", "Timeline": "समय-रेखा", "Calendar": "कैलेंडर", "Memory": "याददाश्त", "Reports": "रिपोर्ट",
    "Schedules": "कॉल का समय", "Family circle": "परिवार", "History": "इतिहास", "Home": "होम", "My family": "मेरा परिवार",
    "My calls": "मेरी बातचीत", "Patients": "मरीज़", "Review queue": "जाँच के लिए", "Behind the call": "कॉल का ख़र्च",
    "Family": "परिवार", "For Appa": "बुज़ुर्गों के लिए", "Care team": "देखभाल टीम", "Log out": "लॉग आउट",
    "Smriti ID": "स्मृति ID", "Demo apps": "डेमो ऐप", "Screen language": "स्क्रीन की भाषा",
    // login
    "Every week, someone remembers": "हर हफ़्ते, कोई याद रखता है",
    "Log in as the family": "परिवार के रूप में लॉग इन करें", "Log in as the elder": "बुज़ुर्ग के रूप में लॉग इन करें",
    "Log in as the care team": "देखभाल टीम के रूप में लॉग इन करें",
    "Demo login: pick a person. No password in the demo.": "डेमो लॉग इन: एक व्यक्ति चुनें। डेमो में पासवर्ड नहीं है।",
    "Other apps": "दूसरे ऐप",
    // greetings
    "Good morning": "सुप्रभात", "Good afternoon": "नमस्ते", "Good evening": "शुभ संध्या",
    // elder home
    "Smriti is here for you. You decide what is shared.": "स्मृति आपके लिए है। क्या बताना है, यह आप तय करते हैं।",
    "Smriti will never ask you for money, bank details or an OTP.": "स्मृति आपसे कभी पैसे, बैंक की जानकारी या OTP नहीं माँगेगी।",
    "{a} wants to add {b}": "{a} चाहते हैं कि {b} को जोड़ा जाए",
    "{b} would see how you are doing, like the rest of your family.": "{b} देख पाएँगे कि आप कैसे हैं, बाक़ी परिवार की तरह।",
    "{b} would see your check results and could order checks.": "{b} आपकी जाँच के नतीजे देख पाएँगे और जाँच करवा सकेंगे।",
    "Yes, add them": "हाँ, जोड़ दीजिए", "No": "नहीं", "Yes": "हाँ",
    "Talk to Smriti now": "अभी स्मृति से बात करें", "Smriti will call your phone for a short chat.": "स्मृति थोड़ी बातचीत के लिए आपको फ़ोन करेगी।",
    "Call me now": "मुझे अभी फ़ोन करें", "My language": "मेरी भाषा",
    "Smriti will speak this. You can also just ask her to switch on a call.": "स्मृति यही भाषा बोलेगी। कॉल पर भी आप भाषा बदलने को कह सकते हैं।",
    "What my family can see": "मेरा परिवार क्या देख सकता है",
    "Only that I'm okay": "बस इतना कि मैं ठीक हूँ", "My family hears that I'm doing well. Nothing more.": "परिवार को बस इतना पता चलेगा कि मैं ठीक हूँ।",
    "Health worries too": "सेहत की चिंता भी", "My family hears about my health worries, in my own words.": "परिवार को मेरी सेहत की चिंता मेरे ही शब्दों में पता चलेगी।",
    "Everything we talk about": "हमारी सारी बातें", "My family hears how I am and what we talked about.": "परिवार को पता चलेगा कि मैं कैसा हूँ और हमने क्या बात की।",
    "If you mention something that sounds like an emergency, our care team will always be told.": "अगर आप कोई आपात बात बताते हैं, तो हमारी देखभाल टीम को हमेशा बताया जाएगा।",
    "Calls": "कॉल", "Calls are paused. Smriti won't call until you turn them back on.": "कॉल रुकी हुई हैं। जब तक आप चालू नहीं करते, स्मृति फ़ोन नहीं करेगी।",
    "Smriti calls at the times your family set. You can pause them any time.": "स्मृति परिवार के तय समय पर फ़ोन करती है। आप कभी भी रोक सकते हैं।",
    "Turn calls back on": "कॉल फिर से चालू करें", "Pause all calls": "सारी कॉल रोकें", "My Smriti ID": "मेरी स्मृति ID",
    "Recently": "हाल में", "Who can see how I am": "कौन देख सकता है कि मैं कैसा हूँ", "Only people you said yes to.": "सिर्फ़ वही लोग जिन्हें आपने हाँ कहा।",
    "My chats with Smriti": "स्मृति से मेरी बातचीत", "In the circle": "परिवार में", "Waiting for the elder": "बुज़ुर्ग की हाँ का इंतज़ार",
    "Done. They're in your circle.": "हो गया। वे अब आपके परिवार में हैं।", "Okay. They won't be added.": "ठीक है। उन्हें नहीं जोड़ा जाएगा।",
    "Smriti will speak {lang}.": "स्मृति {lang} बोलेगी।",
    // family today
    "Here's how {name} has been.": "{name} कैसे रहे, यह देखिए।", "This week": "इस हफ़्ते", "See the timeline": "समय-रेखा देखें",
    "Nothing worrying came up this week.": "इस हफ़्ते कोई चिंता की बात नहीं आई।", "{name} wants you to know": "{name} आपको बताना चाहते हैं",
    "Coming up": "आगे क्या है", "Weekly chat": "हफ़्ते की बातचीत", "Next memory check": "अगली याददाश्त जाँच", "Details": "विवरण",
    "Last chat": "पिछली बातचीत", "Next chat": "अगली बातचीत", "Speaks": "भाषा", "Call {name} now": "{name} को अभी फ़ोन करें",
    "Save Smriti's number": "स्मृति का नंबर सेव करें", "Cheerful": "ख़ुश", "Calm": "शांत", "Low": "उदास",
    // dialogs
    "Phone number": "फ़ोन नंबर", "Who will pick up?": "फ़ोन कौन उठाएगा?", "Cancel": "रद्द करें", "Call now": "अभी फ़ोन करें",
    "Waiting for your family's elder to say yes": "परिवार के बुज़ुर्ग की हाँ का इंतज़ार है",
  },
  kn: {
    "Today": "ಇಂದು", "Timeline": "ಸಮಯರೇಖೆ", "Calendar": "ಕ್ಯಾಲೆಂಡರ್", "Memory": "ನೆನಪು", "Reports": "ವರದಿಗಳು",
    "Schedules": "ಕರೆ ಸಮಯ", "Family circle": "ಕುಟುಂಬ", "History": "ಇತಿಹಾಸ", "Home": "ಮುಖಪುಟ", "My family": "ನನ್ನ ಕುಟುಂಬ",
    "My calls": "ನನ್ನ ಮಾತುಕತೆ", "Patients": "ರೋಗಿಗಳು", "Review queue": "ಪರಿಶೀಲನೆಗೆ", "Behind the call": "ಕರೆಯ ಖರ್ಚು",
    "Family": "ಕುಟುಂಬ", "For Appa": "ಹಿರಿಯರಿಗೆ", "Care team": "ಆರೈಕೆ ತಂಡ", "Log out": "ಲಾಗ್ ಔಟ್",
    "Smriti ID": "ಸ್ಮೃತಿ ID", "Demo apps": "ಡೆಮೊ ಆ್ಯಪ್", "Screen language": "ಪರದೆಯ ಭಾಷೆ",
    "Every week, someone remembers": "ಪ್ರತಿ ವಾರ, ಯಾರೋ ನೆನಪಿಟ್ಟುಕೊಳ್ಳುತ್ತಾರೆ",
    "Log in as the family": "ಕುಟುಂಬದವರಾಗಿ ಲಾಗ್ ಇನ್ ಮಾಡಿ", "Log in as the elder": "ಹಿರಿಯರಾಗಿ ಲಾಗ್ ಇನ್ ಮಾಡಿ",
    "Log in as the care team": "ಆರೈಕೆ ತಂಡವಾಗಿ ಲಾಗ್ ಇನ್ ಮಾಡಿ",
    "Demo login: pick a person. No password in the demo.": "ಡೆಮೊ ಲಾಗ್ ಇನ್: ಒಬ್ಬರನ್ನು ಆರಿಸಿ. ಡೆಮೊದಲ್ಲಿ ಪಾಸ್‌ವರ್ಡ್ ಇಲ್ಲ.",
    "Other apps": "ಇತರ ಆ್ಯಪ್‌ಗಳು",
    "Good morning": "ಶುಭೋದಯ", "Good afternoon": "ನಮಸ್ಕಾರ", "Good evening": "ಶುಭ ಸಂಜೆ",
    "Smriti is here for you. You decide what is shared.": "ಸ್ಮೃತಿ ನಿಮಗಾಗಿ ಇದ್ದಾಳೆ. ಏನು ಹಂಚಿಕೊಳ್ಳಬೇಕು ಎಂಬುದನ್ನು ನೀವೇ ನಿರ್ಧರಿಸುತ್ತೀರಿ.",
    "Smriti will never ask you for money, bank details or an OTP.": "ಸ್ಮೃತಿ ನಿಮ್ಮಿಂದ ಹಣ, ಬ್ಯಾಂಕ್ ವಿವರ ಅಥವಾ OTP ಯಾವತ್ತೂ ಕೇಳುವುದಿಲ್ಲ.",
    "{a} wants to add {b}": "{b} ಅವರನ್ನು ಸೇರಿಸಲು {a} ಬಯಸುತ್ತಾರೆ",
    "{b} would see how you are doing, like the rest of your family.": "ಕುಟುಂಬದ ಇತರರಂತೆ {b} ಅವರೂ ನೀವು ಹೇಗಿದ್ದೀರಿ ಎಂದು ನೋಡಬಹುದು.",
    "{b} would see your check results and could order checks.": "{b} ನಿಮ್ಮ ಪರೀಕ್ಷೆಯ ಫಲಿತಾಂಶ ನೋಡಬಹುದು ಮತ್ತು ಪರೀಕ್ಷೆ ಮಾಡಿಸಬಹುದು.",
    "Yes, add them": "ಹೌದು, ಸೇರಿಸಿ", "No": "ಬೇಡ", "Yes": "ಹೌದು",
    "Talk to Smriti now": "ಈಗ ಸ್ಮೃತಿಯ ಜೊತೆ ಮಾತಾಡಿ", "Smriti will call your phone for a short chat.": "ಸ್ವಲ್ಪ ಮಾತಾಡಲು ಸ್ಮೃತಿ ನಿಮ್ಮ ಫೋನ್‌ಗೆ ಕರೆ ಮಾಡುತ್ತಾಳೆ.",
    "Call me now": "ಈಗ ನನಗೆ ಕರೆ ಮಾಡಿ", "My language": "ನನ್ನ ಭಾಷೆ",
    "Smriti will speak this. You can also just ask her to switch on a call.": "ಸ್ಮೃತಿ ಈ ಭಾಷೆಯಲ್ಲಿ ಮಾತಾಡುತ್ತಾಳೆ. ಕರೆಯಲ್ಲೂ ಭಾಷೆ ಬದಲಿಸಲು ಹೇಳಬಹುದು.",
    "What my family can see": "ನನ್ನ ಕುಟುಂಬ ಏನು ನೋಡಬಹುದು",
    "Only that I'm okay": "ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ ಎಂದು ಮಾತ್ರ", "My family hears that I'm doing well. Nothing more.": "ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ ಎಂದು ಮಾತ್ರ ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಯುತ್ತದೆ.",
    "Health worries too": "ಆರೋಗ್ಯದ ಚಿಂತೆಯೂ", "My family hears about my health worries, in my own words.": "ನನ್ನ ಆರೋಗ್ಯದ ಚಿಂತೆ ನನ್ನದೇ ಮಾತಿನಲ್ಲಿ ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಯುತ್ತದೆ.",
    "Everything we talk about": "ನಾವು ಮಾತಾಡಿದ್ದೆಲ್ಲ", "My family hears how I am and what we talked about.": "ನಾನು ಹೇಗಿದ್ದೇನೆ, ನಾವು ಏನು ಮಾತಾಡಿದೆವು ಎಂದು ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಯುತ್ತದೆ.",
    "If you mention something that sounds like an emergency, our care team will always be told.": "ತುರ್ತು ವಿಷಯ ಹೇಳಿದರೆ, ನಮ್ಮ ಆರೈಕೆ ತಂಡಕ್ಕೆ ಯಾವಾಗಲೂ ತಿಳಿಸಲಾಗುತ್ತದೆ.",
    "Calls": "ಕರೆಗಳು", "Calls are paused. Smriti won't call until you turn them back on.": "ಕರೆಗಳು ನಿಂತಿವೆ. ನೀವು ಮತ್ತೆ ಆನ್ ಮಾಡುವವರೆಗೆ ಸ್ಮೃತಿ ಕರೆ ಮಾಡುವುದಿಲ್ಲ.",
    "Smriti calls at the times your family set. You can pause them any time.": "ಕುಟುಂಬ ಹೇಳಿದ ಸಮಯಕ್ಕೆ ಸ್ಮೃತಿ ಕರೆ ಮಾಡುತ್ತಾಳೆ. ಯಾವಾಗ ಬೇಕಾದರೂ ನಿಲ್ಲಿಸಬಹುದು.",
    "Turn calls back on": "ಕರೆಗಳನ್ನು ಮತ್ತೆ ಆನ್ ಮಾಡಿ", "Pause all calls": "ಎಲ್ಲಾ ಕರೆಗಳನ್ನು ನಿಲ್ಲಿಸಿ", "My Smriti ID": "ನನ್ನ ಸ್ಮೃತಿ ID",
    "Recently": "ಇತ್ತೀಚೆಗೆ", "Who can see how I am": "ನಾನು ಹೇಗಿದ್ದೇನೆ ಎಂದು ಯಾರು ನೋಡಬಹುದು", "Only people you said yes to.": "ನೀವು ಹೌದು ಎಂದವರು ಮಾತ್ರ.",
    "My chats with Smriti": "ಸ್ಮೃತಿಯ ಜೊತೆ ನನ್ನ ಮಾತುಕತೆ", "In the circle": "ಕುಟುಂಬದಲ್ಲಿ", "Waiting for the elder": "ಹಿರಿಯರ ಒಪ್ಪಿಗೆಗೆ ಕಾಯುತ್ತಿದೆ",
    "Done. They're in your circle.": "ಆಯ್ತು. ಅವರು ಈಗ ನಿಮ್ಮ ಕುಟುಂಬದಲ್ಲಿ ಇದ್ದಾರೆ.", "Okay. They won't be added.": "ಸರಿ. ಅವರನ್ನು ಸೇರಿಸುವುದಿಲ್ಲ.",
    "Smriti will speak {lang}.": "ಸ್ಮೃತಿ {lang} ಮಾತಾಡುತ್ತಾಳೆ.",
    "Here's how {name} has been.": "{name} ಹೇಗಿದ್ದಾರೆ ಎಂದು ನೋಡಿ.", "This week": "ಈ ವಾರ", "See the timeline": "ಸಮಯರೇಖೆ ನೋಡಿ",
    "Nothing worrying came up this week.": "ಈ ವಾರ ಚಿಂತೆಯ ವಿಷಯ ಏನೂ ಬರಲಿಲ್ಲ.", "{name} wants you to know": "{name} ನಿಮಗೆ ಹೇಳಲು ಬಯಸುತ್ತಾರೆ",
    "Coming up": "ಮುಂದೆ", "Weekly chat": "ವಾರದ ಮಾತುಕತೆ", "Next memory check": "ಮುಂದಿನ ನೆನಪಿನ ಪರೀಕ್ಷೆ", "Details": "ವಿವರ",
    "Last chat": "ಹಿಂದಿನ ಮಾತುಕತೆ", "Next chat": "ಮುಂದಿನ ಮಾತುಕತೆ", "Speaks": "ಭಾಷೆ", "Call {name} now": "{name} ಅವರಿಗೆ ಈಗ ಕರೆ ಮಾಡಿ",
    "Save Smriti's number": "ಸ್ಮೃತಿಯ ನಂಬರ್ ಉಳಿಸಿ", "Cheerful": "ಖುಷಿ", "Calm": "ಶಾಂತ", "Low": "ಬೇಸರ",
    "Phone number": "ಫೋನ್ ನಂಬರ್", "Who will pick up?": "ಯಾರು ಕರೆ ಸ್ವೀಕರಿಸುತ್ತಾರೆ?", "Cancel": "ರದ್ದು", "Call now": "ಈಗ ಕರೆ ಮಾಡಿ",
    "Waiting for your family's elder to say yes": "ಕುಟುಂಬದ ಹಿರಿಯರ ಒಪ್ಪಿಗೆಗೆ ಕಾಯುತ್ತಿದೆ",
  },
};

function tr(text, vars) {
  let out = (STR[UI_LANG] && STR[UI_LANG][text]) || text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(v);
  return out;
}

function setUiLang(code, remember = false) {
  UI_LANG = UI_LANGS[code] ? code : "en";
  document.documentElement.lang = UI_LANG;
  if (remember) { try { localStorage.setItem("smriti.ui", UI_LANG); } catch { /* private mode */ } }
}

function uiLangSwitch() {
  return `<div class="lang-switch" role="group" aria-label="Screen language">${Object.entries(UI_LANGS).map(([k, v]) =>
    `<button type="button" class="${k === UI_LANG ? "on" : ""}" data-ui-lang="${k}" lang="${k}">${v}</button>`).join("")}</div>`;
}

document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest("[data-ui-lang]");
  if (!b) return;
  setUiLang(b.dataset.uiLang, true);
  if (typeof state !== "undefined" && state.me && state.me.user) route(); else if (typeof showLogin === "function") showLogin();
});

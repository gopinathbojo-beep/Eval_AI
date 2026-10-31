"""The CBSE Class XII Tamil (106) sample question paper 2025-26 (11 pages, 80 marks) as IndicOCR reads it, through the
Tamil format: five பகுதி each followed by its English twin heading, questions 1-15 with parts I. II. III. ...,
each question's own rule ("5x1=5", a lone "5x1=5" block, "[ 2×3=6]"), parts asked for fewer than printed ("[ மூன்று
மட்டும் ]", "எவையேனும் இரண்டனுக்கு"), any-one-topic questions, "Page N of 11" footers. Then a key and a student's
sheet for the roman parts."""
import pytest

from app.ocr.indic import blocks_to_result
from app.ocr.schemas import AnswerKeyPageResult, QuestionPageResult, StudentPageResult
from app.services import paper_format
from app.cbse.common import choices
from app.cbse.common.paper import parse_question_paper_structure
from app.cbse.common.keys import segment_answer_keys
from app.cbse.common.subjects.tamil.answers import one_of_attempts, segment as segment_answers
from app.cbse.common.subjects.tamil.rubric import build_rubric

PAGES = [
    ["மாதிரி வினாத்தாள் - 2025 - 26\nSAMPLE QUESTION PAPER -2025 -26",
     "வகுப்பு: பன்னிரண்டு\n(XII-STD)\nதமிழ்\nTAMIL : 106",
     "மொத்த மதிப்பெண்கள்:80\nMaximum Marks: 80\nகாலஅளவு : 3 மணி\nTime Allowed : 3 Hours",
     "• இந்த வினாத்தாளில் அச்சிடப்பட்ட 11 பக்கங்கள் உள்ளதைச் சரி பார்க்கவும்\n"
     "• இந்த வினாத்தாளில் 15 வினாக்கள் உள்ளனவா எனச் சரிபார்க்கவும்\n"
     "• எழுதத் தொடங்குவதற்கு முன் வினாவரிசை எண்ணைக் குறிப்பிடவும்",
     "• Please check that this question paper contains 11 printed pages\n"
     "• Please check that this question paper contains 15 part of the questions\n"
     "• Please write down the serial number of the question before attempting it.",
     "பகுதி அ (படித்தல் -10 மதிப்பெண்)",
     "Section –A Unseen passage (10 Marks)",
     "1. பின்வரும் உரைநடைப் பகுதியைப் படித்துக் கொடுக்கப்பட்ட பலவுள் தெரிவுசெய் வினாக்களுக்கு விடைதருக.",
     "5x1=5",
     "பாரதியின் கவிதாமண்டலத்தைச் சேர்ந்தவர் என்று பாரதியாரால் முன்மொழியப்பட்டவர் பாரதிதாசன். இவர் சாதி ஒழிப்பு, "
     "பெண் விடுதலை, தமிழ் வளர்ச்சி, மூடப்பழக்க வழக்கங்களை ஒழித்தல் முதலான கருத்துகளுக்கு முக்கியத்துவம் கொடுத்தவர். "
     "மக்கள் இலக்கிய வடிவங்களான கும்மி, தெம்மாங்கு, ஏற்றப்பாட்டு போன்ற வடிவங்களிலும் கவிதை பாடியவர். பழைய யாப்பு "
     "வடிவில் ஆசிரியப்பாவையும் ஆசிரிய விருத்தங்களையும் பாடினார்.",
     "ஓடப்பராயிருக்கும் ஏழையப்பர்\nஉதையப்பராகிவிட்டால் ஓர்நொடிக்குள்",
     "Page 1 of 11"],
    ["ஓடப்பர் உயரப்பர் எல்லாம்மாறி\nஒப்பப்பர் ஆகிவிடுவார் உணரப்பாநீ",
     "பாரதிதாசன் தன்மொழி, தன்னாடு, தன்மக்கள் எனப் பாடியதால் இரஷ்யக் கவிஞரான இரசூல் கம்சதோவ் என்பவரோடு "
     "ஒப்பிடப்படுகிறார். வாணிதாசன், முடியரசன், சுரதா போன்றோர் பாரதிதாசன் பரம்பரைக் கவிஞர்கள் என்று அழைக்கப்படுகின்றனர்.",
     "வினாக்கள்:",
     "I. பாரதிதாசன் பழைய யாப்பு வடிவில் எதைப் பாடினார்?\nA) பாடல்கள் B) கவிதைகள் C) செய்யுட்கள்\nD) ஆசிரியப்பாக்கள்",
     "II. பாரதிதாசனைப் பின்பற்றி எழுதாதவர் யார்?\nA) வாணிதாசன் B) கண்ணதாசன் C) முடியரசன் D) சுரதா",
     "III. ஓடப்பர் உயரப்பர் எல்லாம்மாறி - இவ்வடிகளில் ஓடப்பர் என்பவர் யார்?\nA) பணக்காரர் B) நடுத்தர மக்கள் C) ஏழையோர்\nD) மூன்றும் சரி",
     "IV. இரசூல் கம்சதோவ் எந்நாட்டைச் சார்ந்தவர்?\nA) ஜெர்மன் B) இந்தியா C) தமிழ்நாடு D) இரஷ்யா",
     "V. மக்கள் இலக்கிய வடிவம் எது?\nA) கதை B) கவிதை C) உரைநடை D) கும்மி",
     "2. பின்வரும் உரைநடைப்பகுதியைப் படித்துக் கொடுக்கப்பட்ட\nவினாக்களுக்கு விடை தருக. 5x1=5",
     "தமிழக வரலாற்றில் தொன்மங்களின் கூறுகளாகப் பண்பாடு சார்ந்தும், பண்டைய தமிழர்களின் மரபு சார்ந்தும் தொன்றுதொட்டு பல "
     "விழாக்கள் நடைபெற்றுக் கொண்டிருக்கின்றன. அப்படி நடக்கின்ற விழாக்களில் ஒன்றுதான் ஆடிப்பெருக்கு விழா.",
     "Page 2 of 11"],
    ["ஆடிப் பெருக்கு திருநாளை 'சப்த கன்னி'களுக்கு நடத்தப்படுகிற ஒரு விழாவாகவே வரலாறு காட்டுகிறது. நீரும் மண்ணும் "
     "பயிரும்தான் நம் மக்களை இயங்க வைக்கும், இயக்கவும் வைக்கும். நீரின்றி அமையாது உலகு.",
     "வினாக்கள்:",
     "I. ஆடிப்பெருக்கு யாருக்கு உரியது என வரலாறு கூறுகிறது.?\nII. மக்களை இயக்குவது எது?\n"
     "III. வேளாண்மை எப்போது உயர்ந்திருக்கும்?\nIV. தமிழர்கள் தேதி பார்த்துக் கொண்டாடும் விழாக்கள் எவை?\n"
     "V. நீரின்றி அமையாது உலகு - இது யாருடைய கூற்று?",
     "பகுதி -ஆ(இலக்கணம் -12 மதிப்பெண்)\nSection – B ( Grammar-12 Marks)",
     "3. பிழை நீக்கித் திருத்தப்பட்ட தொடர் எதுவெனக் கண்டறிந்து எழுதுக [ மூன்று மட்டும் ] 3x1=3",
     "Page 3 of 11"],
    ["I. இன்ணலிலே இருக்கும் தொழிளாலர்களை நாம் நினைக்க வேண்டும்.\nA) இன்னலிலே இருக்கும் தொழிளாலர்களை நாம் நினைக்க வேண்டும்.\n"
     "B) இண்ணலிலே இருக்கும் தொழிளாலர்களை தாம் நினைக்க வேண்டும்.\nC) இன்னலிலே இருக்கும் தொழிலாளர்களை நாம் நினைக்க வேண்டும்.\n"
     "D) இன்னலிலே இருக்கும் தொலிழாளர்களை நாம் நிணைக்க வேண்டும்.",
     "II. என் மணம் பறந்து நின்ற மரக்கிலையிலிருந்து பரிக்கப்பட்ட மளர்போல் வாடுகிறது.\n"
     "A) எண் மணம் பரந்து நின்ற மரக்கிளையிலிருந்து பறிக்கப்பட்ட மலர்போல் வாடுகிறது.\n"
     "D) என் மனம் பரந்து நின்ற மரக்கிளையிலிருந்து பறிக்கப்பட்ட மலர்போல் வாடுகிறது.",
     "III. கருத்தாளமும் வாசகச் சுவைப்பும் கலந்து இலக்கியங்கள் படைத்தவர் ஜெயகாந்தன்\n"
     "A) கறுத்தாழமும் வாசகச் சுவைப்பும் கலந்து இலக்கியங்கள். படைத்தவர் ஜெயகாந்தன்.\n"
     "B) கருத்தாழமும் வாசகச் சுவைப்பும் கலந்து இலக்கியங்கள். படைத்தவர் ஜெயகாந்தன்.",
     "IV. சட்டையில் படிந்துள்ள கறையைப் போக்கு.\nA) சட்டையிள் படிந்துள்ள கறையைப் போக்கு\nB) சட்டையில் படிந்துள்ள கறையைப் போக்கு\n"
     "C) சட்டையில் படிந்துள்ள கரையைப் போக்கு\nD) சட்டையில் பரிந்துல்ல கரையைப் பேயக்கு",
     "Page 4 of 11"],
    ["V. வரண்டு கிடந்த புலுதிநிலம் வலம்பெற மழை பொழிய வேண்டும்.\nA) வரண்டு கிடந்த புளுதிநிலம் வலம்பெற மழை பொழிய வேண்டும்.\n"
     "C) வறண்டு கிடந்த புழுதிநிலம் வளம்பெற மழை பொழிய வேண்டும்.",
     "4. வல்லினமெய்யிட்டுத் திருத்தியதொடர் எதுவெனக் கண்டறிந்து எழுதுக [ மூன்று மட்டும் ] 3x1=3",
     "I. திறனாய்வு கலையை தமிழுக்கு அறிமுகப்படுத்தியவர் தி.சு. நடராசன்.\nA) திறனாய்வுக் கலையைத் தமிழுக்கு அறிமுகப்படுத்தியவர் தி.சு. நடராசன்",
     "II. பேருந்தை பிடிக்க சாலைகயை கடக்க இரு பக்கங்களையும் பார்.\nC) பேருந்தைப் பிடிக்கச் சாலையைக் கடக்க இருபக்கங்களையும் பார்.",
     "III. காவடிபாரம் சுமக்கிறவனுக்கு தெரியும்\nC) காவடிப்பாரம் சுமக்கிறவனுக்குத் தெரியும்",
     "IV. காக்கைக்கு தன் குஞ்சு பொன்குஞ்சு\nA) காக்கைக்குத் தன் குஞ்சு பொன்குஞ்சு",
     "Page 5 of 11"],
    ["V. அறியா பிள்ளை செய்த பிழையால் தீரா துன்பம் அடைந்தான் .\nA) அறியாப்பிள்ளை செய்த பிழையால் தீராத்துன்பம் அடைந்தான்.",
     "5. எடுத்துக்காட்டு எழுதுக [மூன்று மட்டும்] 3x1=3",
     "I. உணர்ச்சி வாக்கியம் (வியப்பு)\nA) மாணவர்கள் அனைவரும் தேர்ச்சி பெற்றனரே!\nD) ஆ! தாஜ்மகாலின் அழகுதான் என்னே!",
     "II. நேர்க்கூற்று வாக்கியம்.\nA) \"போருக்கு இன்று போய் நாளை வா\" என்று இராமன் கூறினான்",
     "III. விழைவு வாக்கியம் (ஏவல்-விழைவு)\nA) பாடல்களை நன்றாகப் படி\nC) பல்லாண்டு வாழ்க",
     "IV. தொடர் வாக்கியம்\nA) மணிமேகலை படித்தாள்; முதன்மையாகத் தேறினாள்; பரிசு பெற்றாள்\nD) கயல்விழி கற்றாள்.",
     "Page 6 of 11"],
    ["V. செயப்பாட்டு வினைத் தொடர்.\nA) கோவலன் கொலையுண்டான்.\nD) கோவலன் கொலை செய்யப்பட்டான்.",
     "6. வழுவற்ற தொடரைத் தேர்வு செய்து எழுதுக [மூன்று மட்டும்]",
     "3x1=3",
     "I",
     "A) தீய பண்புகள் வாழ்வைக் கெடுத்தது\nB) தீய பண்பு வாழ்வைக் கெடுத்தன\nC) தீய பண்புகள் வாழ்வைக் கெடுத்தன\nD) தீய பண்புகள் வாழ்வைக் கெடுக்காது",
     "II.\nA) கூட்டத்தில் அறிஞர் பலர் பேசினர்\nB) கூட்டத்தில் பல அறிஞர் பேசினர்",
     "III.\nA) பொன்னனும் எருதும் வந்தன\nD) பொன்னனும் எருதும் வந்தனர்.",
     "IV.\nA) வலது பக்கச் சுவரில் எழுதாதே.\nB) வலப்பக்கச் சுவரில் எழுதாதே",
     "V.\nA) அவள் கொடுத்த நூல் அது அல்ல\nC) அவள் கொடுத்த நூல் அது அன்று.",
     "Page 7 of 11"],
    ["பகுதி -இ (இலக்கியம் -31 மதிப்பெண்)",
     "Section –C ( Main course book 31 Marks)",
     "7. பின்வரும் செய்யுள் அடிகளைப் படித்து அதனைத் தொடர்ந்து வரும் வினாக்களுக்கு விடையளி: (5x1=5)",
     "வையகம் பனிப்ப, வலன் ஏர்பு வளைஇ,\nபொய்யா வானம் புதுப்பெயல் பொழிந்தென,\n"
     "ஆர்கலி முனைஇய கொடுங்கோல் கோவலர்,\nஏறுடை இனநிரை வேறுபுலம் பரப்பி -",
     "வினாக்கள்:",
     "I. மேற்கண்ட அடிகளில் 'மழை' எனப் பொருள் தரும் சொல் எது?\nA) வளை B) ஆர்கலி C) வலனேர்பு D) பெயல்",
     "II. நிரை என்ற சொல்லின் பொருள் ________\nA) எருமை B) பசு C) ஆடு D) மூன்றும் சேர்ந்தது",
     "III. இவ்வடிகளை எழுதியவர் யார்?\nA) மதுரைக் கணக்காயனார் B) நக்கீரர் C) மாதவன் அய்யப்பன் D) கம்பர்",
     "IV. கோவலர் என்போர் ________\nA) ஆயர் B) உழவர் C) எயினர் D) பரதர்",
     "V. இப்பாடலடிகள் இடம்பெற்ற நூல் எது?\nA) கம்பராமாயணம் B) குறுந்தொகை C) நெடுநல்வாடை\nD).பரிபாடல்",
     "8. பின்வரும் பத்தியைப் படித்து அதனைத் தொடர்ந்து வரும் வினாக்களுக்கு விடையளி: 5×1=5",
     "இலக்கியத்தின் பயன் பற்றித் தமிழ் இலக்கிய மரபில் அழுத்தமான கருத்து உண்டு. அறம், பொருள், இன்பமாகவோ அல்லது வேறு "
     "ஏதோ ஓர் உயர்ந்த குறிக்கோளாகவோ, இந்தப் பயன் இலக்கிய உருவாக்கத்தில் இடம்பெற வேண்டும்.",
     "Page 8 of 11"],
    ["இத்தகையதொரு முழுமைதான், கலை முழுமை (artistic whole) எனப்படுகிறது. பா வகைகள் ஆசிரியம் முதற்கொண்டு நான்கு எனச் "
     "சொல்லிவிட்டுத் தொடர்ந்து, பண்பாட்டின் இலச்சினையாகச்\n(symbol of culture) சித்தரிப்பதற்குத் தமிழ்மரபு முன்வந்திருக்கிறது.",
     "வினாக்கள் :",
     "I. .பா வகைகள் மொத்தம் எத்தனை?\nII. 'இலக்கியத்தின் பயன்' எதுவாக அமைய வேண்டும்?\n"
     "III. பாடற்பொருள்களாக சங்க இலக்கியம் எவற்றைக் கொண்டுள்ளது?\nIV. தமிழ்மரபு எதற்கு தயாராகியிருக்கிறது?\n"
     "V. இப்பத்தியில் குறிப்பிடப்படும் இலக்கண நூல் எது?",
     "9. பின்வரும் செய்யுள் வினாக்களில் எவையேனும் இரண்டனுக்குச் சுருக்கமான விடையளி [ 2×3=6]",
     "I. வள்ளலார் இறைவனிடம் வேண்டுவன யாவை?",
     "II. தலைவன் பாங்கனுக்கு கூறியதை எழுதுக.",
     "III. பிறகொடுநாள்கோடை - மாதவனின் கருத்தை விளக்குக.",
     "IV. இராமன் சடாயுவுக்கு இறுதிச்சடங்கு செய்த முறையை எழுதுக ?",
     "Page 9 of 11"],
    ["10. பின்வரும் உரைநடை வினாக்களில் எவையேனும் மூன்றனுக்கு விடையளி. 3×5=15",
     "I. மணந்தகம்-விளக்குக.\nII. அறிவின் நகரம் சென்னை - விளக்குக.\n"
     "III. பேரிடர் வராமல் இருக்கவும், வந்தால் செய்ய வேண்டுவனவும் யாவை?\nIV. தமிழின் தொடரியல் போக்குகளை விளக்குக.\n"
     "V. சென்னையின் பண்பாட்டு அடையாளங்களாக இன்றும் நிற்பவை எவை?",
     "பகுதி -ஈ (துணைப்பாடம் -12 மதிப்பெண்)\nSection – D ( Non-detail - 12 Marks)",
     "11. ஏதேனும் ஒன்று குறித்து துணைப்பாடக் கட்டுரை எழுதுக 1x7=7",
     "I. முதல்கல். II. தலைக்குளம் III. உரிமைத்தாகம்",
     "12. கீழ்காணும் கதைமாந்தரில் ஒருவரின் பண்பு நலனை எழுதுக 1×5=5",
     "I. மருதன் II. முத்தையன்",
     "பகுதி -உ( படைப்புத்திறன் -15 மதிப்பெண்)\nSection – E ( Creative writing - 15 Marks)",
     "13. பின்வரும் தலைப்புகளில் ஒன்று பற்றிக் கடிதம் வரைக. 1×6=6",
     "I. நடைபெற்று வரும் மட்டைப்பந்து உலகக்கோப்பை போட்டி பற்றி உன் நண்பனுக்குக் கடிதம் எழுதுக.\n"
     "II. உன் பகுதியில் இயங்கிவரும் அரசு பொது மருத்துவமனைக்கு போதிய மருத்துவர்களை நியமிக்க வேண்டி முதலமைச்சருக்கு "
     "விண்ணப்பக் கடிதம் வரைக.\n( உனது முகவரி: பா.இனியவன் /பா.இனியாள், 23, வள்ளலார் நகர், கடலூர். 607001)",
     "Page 10 of 11"],
    ["14. நல்லாசிரியர் விருது பெற்ற தமிழ்ப் பேராசிரியர் ஒருவரை நேர்காணல் செய்க. 1×3=3",
     "15. பின்வரும் தலைப்புகளில் ஒன்று குறித்துக் கட்டுரை எழுதுக.\n1x6=6",
     "I. புவி வெப்பமயமாதல்\nII. தாய்மொழிக் கல்வி\nIII. இந்தியாவின் மக்களாட்சி",
     "Page 11 of 11"],
]


def _pages(raw, schema):
    return [({"page_number": i}, blocks_to_result({"blocks": [{"order": n, "type": "Text", "text": t} for n, t in enumerate(p)]}, schema, i))
            for i, p in enumerate(raw, 1)]


@pytest.fixture(autouse=True)
def _tamil_subject():
    with paper_format.use(paper_format.TAMIL):
        yield


@pytest.fixture(scope="module")
def doc():
    with paper_format.use(paper_format.TAMIL):
        return parse_question_paper_structure(_pages(PAGES, QuestionPageResult))


def _by(doc):
    return {q.display_number: q for q in doc.questions}


def _numerals(n):
    return ["I", "II", "III", "IV", "V"][:n]


def test_header_total_and_duration(doc):
    assert doc.exam_max_marks == 80 and doc.exam_duration_minutes == 180


def test_every_question_and_part_once_in_order(doc):
    expected = [f"{q}({r})" for q, n in ((1, 5), (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5), (8, 5), (9, 4), (10, 5))
                for r in _numerals(n)] + ["11", "12", "13", "14", "15"]
    assert [q.display_number for q in doc.questions] == expected
    assert [q.normalized_number for q in doc.questions][:2] == ["1(i)", "1(ii)"]
    assert all(q.verification_status == "UNVERIFIED" for q in doc.questions)


def test_five_sections_without_their_english_twins(doc):
    tops = [s for s in doc.sections if " / " not in s]
    assert [s.split("(")[0].strip() for s in tops] == ["பகுதி அ", "பகுதி -ஆ", "பகுதி -இ", "பகுதி -ஈ", "பகுதி -உ"]
    assert not any(s.startswith("Section") for s in doc.sections)


def test_marks_per_part_and_paper_total_80(doc):
    by = _by(doc)
    assert {by[f"{q}({r})"].max_marks for q in range(1, 9) for r in _numerals(5)} == {1}
    assert {by[f"9({r})"].max_marks for r in _numerals(4)} == {3}
    assert {by[f"10({r})"].max_marks for r in _numerals(5)} == {5}
    assert [by[n].max_marks for n in ("11", "12", "13", "14", "15")] == [7, 5, 6, 3, 6]
    assert choices.max_total(doc.questions) == 80


def test_any_n_of_a_questions_parts(doc):
    by = _by(doc)
    for q, n, parts in ((3, 3, 5), (4, 3, 5), (5, 3, 5), (6, 3, 5), (9, 2, 4), (10, 3, 5)):
        qs = [by[f"{q}({r})"] for r in _numerals(parts)]
        assert {x.answer_any for x in qs} == {n} and len({x.section for x in qs}) == 1
        assert qs[0].section.endswith(f"/ வினா {q}")
    assert {by[f"1({r})"].answer_any for r in _numerals(5)} == {None}
    assert by["1(I)"].section == by["2(I)"].section and "/" not in by["1(I)"].section


def test_parts_carry_their_passage_or_instruction(doc):
    by = _by(doc)
    one = by["1(II)"].question_text
    assert one.startswith("[Reading Passage Context]") and "கண்ணதாசன்" in one and "பாரதிதாசன் பரம்பரைக் கவிஞர்கள்" in one
    assert "ஏறுடை இனநிரை" in by["7(IV)"].question_text
    assert by["6(I)"].question_text.startswith("வழுவற்ற தொடரைத்") and "தீய பண்புகள் வாழ்வைக் கெடுத்தன" in by["6(I)"].question_text
    assert "வேளாண்மை" in by["2(III)"].question_text and "தமிழர்கள் தேதி" not in by["2(III)"].question_text
    assert not any("Page" in q.question_text for q in doc.questions)


def test_types(doc):
    by = _by(doc)
    assert {by[f"{q}({r})"].question_type for q in (1, 7) for r in _numerals(5)} == {"mcq"}
    assert by["3(I)"].question_type == "mcq" and by["6(I)"].question_type == "mcq"
    assert by["13"].question_type == "descriptive" and by["15"].question_type == "descriptive"


def test_a_part_numbered_like_a_section_stays_a_part(doc):
    by = _by(doc)
    assert "தலைவன் பாங்கனுக்கு" in by["9(II)"].question_text and "சடாயுவுக்கு" in by["9(IV)"].question_text


def test_any_one_topic_stays_one_question_and_attempts_split_by_numeral(doc):
    q15 = _by(doc)["15"]
    assert "தாய்மொழிக் கல்வி" in q15.question_text and q15.answer_any is None
    got = one_of_attempts(q15.question_text, "I. புவி வெப்பமயமாதல்\nபுவியின் வெப்பம் உயர்கிறது.\nII. தாய்மொழிக் கல்வி\nதாய்மொழியில் கற்றல் எளிது.")
    assert [h for h, _ in got] == ["I. புவி வெப்பமயமாதல்", "II. தாய்மொழிக் கல்வி"]


KEY = [[
    "1. I. D) ஆசிரியப்பாக்கள்\nII. B) கண்ணதாசன்\nIII. C) ஏழையோர்\nIV. D) இரஷ்யா\nV. D) கும்மி",
    "2. I. சப்த கன்னிகளுக்கு உரியது.\nII. நீரும் மண்ணும் பயிரும்\nIII. பிறையின் வடகோடி உயர்ந்திருந்தால்\n"
    "IV. ஆடிப்பெருக்கு, பொங்கல்\nV. திருவள்ளுவர்",
]]


def test_key_split_into_its_roman_parts(doc):
    keys = {k.normalized_number: k for k in segment_answer_keys(_pages(KEY, AnswerKeyPageResult), doc.questions)}
    assert "ஆசிரியப்பாக்கள்" in keys["1(i)"].answer_text and "கண்ணதாசன்" not in keys["1(i)"].answer_text
    assert "கும்மி" in keys["1(v)"].answer_text and "திருவள்ளுவர்" in keys["2(v)"].answer_text
    assert keys["1(iii)"].marks == 1
    by = _by(doc)
    point = build_rubric(by["1(I)"].question_text, keys["1(i)"].answer_text, keys["1(i)"].criteria, 1).criteria[0]
    assert point.marks == 1 and "ஆசிரியப்பாக்கள்" in point.text and "(i)" not in point.text


def test_student_answers_split_into_parts_any_three_skipping(doc):
    sheet = [["1. I. D) ஆசிரியப்பாக்கள்\nII. B) கண்ணதாசன்\nIII. C) ஏழையோர்",
              "IV", "D) இரஷ்யா", "3. I. C\nIII. B\nV. C"]]
    answers = segment_answers(_pages(sheet, StudentPageResult), doc.questions)
    got = {a.normalized_number: a.answer_text for a in answers}
    assert "ஆசிரியப்பாக்கள்" in got["1(i)"] and "கண்ணதாசன்" in got["1(ii)"] and "இரஷ்யா" in got["1(iv)"]
    assert {n for n in got if n.startswith("3")} == {"3(i)", "3(iii)", "3(v)"}
    assert "4" not in got

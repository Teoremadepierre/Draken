#!/usr/bin/env python3
"""Authoring tool for ``data/seeds/link_sources.json``.

The JSON file is the runtime source of truth (and is human-editable); this script
is how it is generated and kept consistent. Re-run after editing the tables here:

    python3 scripts/build_link_source_seed.py

Field notes
-----------
authority            estimated domain authority 0-100 (order-of-magnitude, not gospel)
effort               1 = paste a URL, 5 = write an article / needs an editor
automatable          a deterministic form/API exists -> the submission runner can prefill
llm_citation_weight  0..1 - how often this domain shows up as a source in LLM answers
ai_training_signal   the corpus is known to be heavily used for model training/grounding
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "seeds" / "link_sources.json"

ROWS: list[dict] = []


def add(
    slug: str,
    name: str,
    domain: str,
    category: str,
    authority: int,
    *,
    submit_url: str = "",
    link_type: str = "nofollow",
    is_free: bool = True,
    requires_account: bool = True,
    requires_moderation: bool = True,
    automatable: bool = False,
    effort: int = 2,
    countries: tuple[str, ...] = ("*",),
    languages: tuple[str, ...] = ("*",),
    industries: tuple[str, ...] = ("*",),
    tags: tuple[str, ...] = (),
    required_fields: tuple[str, ...] = ("display_name", "website", "short_description"),
    guidelines_url: str = "",
    notes: str = "",
    ai_training_signal: bool = False,
    llm_citation_weight: float = 0.0,
    adapter: str = "",
) -> None:
    ROWS.append(
        {
            "slug": slug,
            "name": name,
            "domain": domain,
            "submit_url": submit_url or f"https://{domain}",
            "category": category,
            "authority": float(authority),
            "link_type": link_type,
            "is_free": is_free,
            "requires_account": requires_account,
            "requires_moderation": requires_moderation,
            "automatable": automatable,
            "effort": effort,
            "countries": list(countries),
            "languages": list(languages),
            "industries": list(industries),
            "tags": list(tags),
            "required_fields": list(required_fields),
            "guidelines_url": guidelines_url,
            "notes": notes,
            "ai_training_signal": ai_training_signal,
            "llm_citation_weight": llm_citation_weight,
            "adapter": adapter,
        }
    )


NAP = ("display_name", "website", "short_description", "phone", "street", "city", "postal_code", "country")
NAP_LITE = ("display_name", "website", "short_description", "city", "country")
PROFILE = ("display_name", "website", "short_description", "logo_url")

# ---------------------------------------------------------------------------
# 1. Map / search engine business profiles - the foundation of local SEO
# ---------------------------------------------------------------------------
add("google-business-profile", "Google Business Profile", "business.google.com", "business_profile", 100,
    submit_url="https://business.google.com/create", link_type="nofollow", effort=3, required_fields=NAP,
    tags=("local", "map", "foundation", "verification-required"), llm_citation_weight=0.55,
    notes="Non-negotiable first step for any local entity. Drives the Google knowledge panel that AI answers reuse.")
add("bing-places", "Bing Places for Business", "bingplaces.com", "business_profile", 92,
    submit_url="https://www.bingplaces.com/", effort=2, required_fields=NAP, automatable=False,
    tags=("local", "map", "foundation"), llm_citation_weight=0.45,
    notes="Feeds Bing + Copilot local results. Can bulk-import straight from Google Business Profile.")
add("apple-business-connect", "Apple Business Connect", "businessconnect.apple.com", "business_profile", 94,
    submit_url="https://businessconnect.apple.com/", effort=3, required_fields=NAP,
    tags=("local", "map", "foundation"), llm_citation_weight=0.2,
    notes="Powers Apple Maps and Siri. Free 'Showcases' act as mini landing pages.")
add("yandex-business", "Yandex Business", "yandex.com", "business_profile", 93,
    submit_url="https://yandex.com/sprav/", effort=3, required_fields=NAP,
    countries=("RU", "TR", "KZ", "BY", "UZ"), tags=("local", "map"),
    notes="Only worth it if you target RU/TR/CIS traffic.")
add("openstreetmap", "OpenStreetMap", "openstreetmap.org", "wiki", 92,
    submit_url="https://www.openstreetmap.org/", link_type="dofollow", effort=3,
    required_fields=NAP, tags=("map", "open-data", "citation-source"),
    ai_training_signal=True, llm_citation_weight=0.35,
    guidelines_url="https://wiki.openstreetmap.org/wiki/Good_practice",
    notes="Open data: your entry propagates into dozens of downstream maps and datasets. Add real, verifiable data only.")
add("here-places", "HERE Map Feedback", "here.com", "business_profile", 85,
    submit_url="https://mapcreator.here.com/", effort=3, required_fields=NAP, tags=("map",),
    notes="Feeds in-car navigation systems and several fleet apps.")
add("tomtom-mapshare", "TomTom MapShare", "tomtom.com", "business_profile", 87,
    submit_url="https://mapshare.tomtom.com/", effort=3, required_fields=NAP, tags=("map",))
add("waze-business", "Waze for Business", "waze.com", "business_profile", 91,
    submit_url="https://www.waze.com/business/", effort=2, required_fields=NAP, tags=("local", "map"))
add("nextdoor-business", "Nextdoor Business", "nextdoor.com", "business_profile", 89,
    submit_url="https://business.nextdoor.com/", effort=2, required_fields=NAP,
    countries=("US", "GB", "CA", "AU", "NL", "DE", "FR", "ES"), tags=("local", "neighbourhood"))

# ---------------------------------------------------------------------------
# 2. Global business directories / local citations
# ---------------------------------------------------------------------------
_DIRS = [
    ("yelp", "Yelp for Business", "yelp.com", 94, "https://biz.yelp.com/signup", 0.4, True),
    ("foursquare", "Foursquare Places", "foursquare.com", 91, "https://foursquare.com/add-place", 0.25, True),
    ("yellowpages-us", "Yellow Pages (US)", "yellowpages.com", 89, "https://accounts.yellowpages.com/register", 0.15, False),
    ("superpages", "Superpages", "superpages.com", 80, "https://www.superpages.com/", 0.05, False),
    ("manta", "Manta", "manta.com", 78, "https://www.manta.com/claim", 0.05, False),
    ("chamberofcommerce", "ChamberofCommerce.com", "chamberofcommerce.com", 75, "https://www.chamberofcommerce.com/", 0.05, False),
    ("merchantcircle", "MerchantCircle", "merchantcircle.com", 73, "https://www.merchantcircle.com/signup", 0.02, False),
    ("hotfrog", "Hotfrog", "hotfrog.com", 72, "https://www.hotfrog.com/AddYourBusiness", 0.02, True),
    ("cylex", "Cylex", "cylex.us.com", 68, "https://www.cylex.us.com/company-registration.html", 0.02, True),
    ("brownbook", "Brownbook", "brownbook.net", 70, "https://www.brownbook.net/register/", 0.02, True),
    ("tupalo", "Tupalo", "tupalo.com", 67, "https://tupalo.com/en/add-business", 0.02, True),
    ("showmelocal", "ShowMeLocal", "showmelocal.com", 62, "https://www.showmelocal.com/addbusiness.aspx", 0.0, True),
    ("ezlocal", "EZlocal", "ezlocal.com", 60, "https://ezlocal.com/add-business", 0.0, True),
    ("citysearch", "Citysearch", "citysearch.com", 76, "https://www.citysearch.com/", 0.02, False),
    ("local-com", "Local.com", "local.com", 71, "https://www.local.com/", 0.0, False),
    ("yellowbot", "YellowBot", "yellowbot.com", 61, "https://www.yellowbot.com/", 0.0, True),
    ("opendi", "Opendi", "opendi.com", 59, "https://www.opendi.com/", 0.0, True),
    ("tuugo", "Tuugo", "tuugo.info", 57, "https://www.tuugo.info/", 0.0, True),
    ("cybo", "Cybo", "cybo.com", 58, "https://www.cybo.com/", 0.0, True),
    ("fyple", "Fyple", "fyple.com", 55, "https://www.fyple.com/", 0.0, True),
    ("infobel", "Infobel", "infobel.com", 66, "https://www.infobel.com/", 0.0, True),
    ("yalwa", "Yalwa", "yalwa.com", 58, "https://www.yalwa.com/", 0.0, True),
    ("lacartes", "Lacartes", "lacartes.com", 52, "https://www.lacartes.com/", 0.0, True),
    ("ibegin", "iBegin", "ibegin.com", 54, "https://www.ibegin.com/", 0.0, True),
    ("n49", "n49", "n49.com", 56, "https://www.n49.com/", 0.0, True),
    ("golocal247", "GoLocal247", "golocal247.com", 50, "https://www.golocal247.com/", 0.0, True),
    ("callupcontact", "CallUpContact", "callupcontact.com", 49, "https://www.callupcontact.com/", 0.0, True),
    ("where-to", "Where To?", "where-to.co.uk", 47, "https://www.where-to.co.uk/", 0.0, True),
    ("bizhwy", "BizHwy", "bizhwy.com", 45, "https://www.bizhwy.com/", 0.0, True),
    ("elocal", "eLocal", "elocal.com", 63, "https://www.elocal.com/", 0.0, False),
]
for slug, name, domain, auth, url, weight, autom in _DIRS:
    add(slug, name, domain, "local_citation", auth, submit_url=url, effort=2, required_fields=NAP,
        automatable=autom, tags=("local", "citation", "nap"), llm_citation_weight=weight,
        notes="Citation consistency play: exact same NAP as every other listing.")

# ---------------------------------------------------------------------------
# 3. Spain / LatAm directories (primary market for Spanish-language projects)
# ---------------------------------------------------------------------------
_ES = [
    ("paginas-amarillas-es", "Páginas Amarillas", "paginasamarillas.es", 78, "https://www.paginasamarillas.es/", ("ES",)),
    ("qdq", "QDQ", "qdq.com", 71, "https://www.qdq.com/", ("ES",)),
    ("11870", "11870.com", "11870.com", 66, "https://11870.com/", ("ES",)),
    ("infoempresa", "Infoempresa", "infoempresa.com", 70, "https://www.infoempresa.com/", ("ES",)),
    ("einforma", "eInforma", "einforma.com", 72, "https://www.einforma.com/", ("ES",)),
    ("axesor", "Axesor", "axesor.es", 69, "https://www.axesor.es/", ("ES",)),
    ("empresite", "Empresite (El Economista)", "empresite.eleconomista.es", 74, "https://empresite.eleconomista.es/", ("ES",)),
    ("solostocks", "SoloStocks", "solostocks.com", 73, "https://www.solostocks.com/", ("ES", "MX", "CO")),
    ("europages", "Europages", "europages.co.uk", 80, "https://www.europages.co.uk/", ("ES", "FR", "DE", "IT", "*")),
    ("guialocal-es", "Guíalocal", "guialocal.es", 54, "https://www.guialocal.es/", ("ES",)),
    ("habitissimo", "Habitissimo", "habitissimo.es", 70, "https://www.habitissimo.es/", ("ES", "IT", "PT", "BR")),
    ("cylex-es", "Cylex España", "cylex.es", 62, "https://www.cylex.es/", ("ES",)),
    ("tupalo-es", "Tupalo España", "tupalo.es", 58, "https://tupalo.es/", ("ES",)),
    ("amarillas-internet", "Amarillas Internet", "amarillasinternet.com", 52, "https://www.amarillasinternet.com/", ("MX", "AR", "CO", "CL", "PE")),
    ("paginas-amarillas-co", "Páginas Amarillas Colombia", "paginasamarillas.com.co", 63, "https://www.paginasamarillas.com.co/", ("CO",)),
    ("seccion-amarilla", "Sección Amarilla", "seccionamarilla.com.mx", 68, "https://www.seccionamarilla.com.mx/", ("MX",)),
    ("guia-local-ar", "Guíalocal Argentina", "guialocal.com.ar", 50, "https://www.guialocal.com.ar/", ("AR",)),
    ("dateas", "Dateas", "dateas.com", 59, "https://www.dateas.com/", ("AR",)),
    ("emis-latam", "EMIS LatAm business profiles", "emis.com", 71, "https://www.emis.com/", ("BR", "MX", "AR", "CO")),
]
for slug, name, domain, auth, url, countries in _ES:
    add(slug, name, domain, "local_citation", auth, submit_url=url, effort=2, required_fields=NAP,
        countries=countries, languages=("es",), tags=("local", "citation", "spanish-market"),
        notes="Alta relevancia para proyectos en español: mantén el NAP idéntico en todos los listados.")

# ---------------------------------------------------------------------------
# 4. Review & B2B buyer platforms (huge LLM citation weight)
# ---------------------------------------------------------------------------
_REVIEWS = [
    ("trustpilot", "Trustpilot", "trustpilot.com", 93, "https://business.trustpilot.com/signup", 0.6, "dofollow"),
    ("g2", "G2", "g2.com", 92, "https://www.g2.com/products/new", 0.75, "nofollow"),
    ("capterra", "Capterra", "capterra.com", 91, "https://www.capterra.com/vendors/sign-up", 0.6, "nofollow"),
    ("getapp", "GetApp", "getapp.com", 88, "https://www.getapp.com/vendors/", 0.4, "nofollow"),
    ("software-advice", "Software Advice", "softwareadvice.com", 87, "https://www.softwareadvice.com/vendors/", 0.35, "nofollow"),
    ("trustradius", "TrustRadius", "trustradius.com", 86, "https://www.trustradius.com/vendors", 0.45, "nofollow"),
    ("sitejabber", "Sitejabber", "sitejabber.com", 80, "https://www.sitejabber.com/", 0.2, "nofollow"),
    ("clutch", "Clutch", "clutch.co", 89, "https://clutch.co/get-listed", 0.55, "dofollow"),
    ("goodfirms", "GoodFirms", "goodfirms.co", 82, "https://www.goodfirms.co/get-listed", 0.3, "dofollow"),
    ("designrush", "DesignRush", "designrush.com", 79, "https://www.designrush.com/agency/submit", 0.25, "dofollow"),
    ("sortlist", "Sortlist", "sortlist.com", 78, "https://www.sortlist.com/", 0.2, "nofollow"),
    ("upcity", "UpCity", "upcity.com", 77, "https://upcity.com/get-listed/", 0.2, "dofollow"),
    ("the-manifest", "The Manifest", "themanifest.com", 76, "https://themanifest.com/get-listed", 0.2, "dofollow"),
    ("expertise", "Expertise.com", "expertise.com", 75, "https://www.expertise.com/", 0.15, "nofollow"),
    ("resellerratings", "ResellerRatings", "resellerratings.com", 74, "https://www.resellerratings.com/", 0.1, "nofollow"),
]
for slug, name, domain, auth, url, weight, lt in _REVIEWS:
    add(slug, name, domain, "review_platform", auth, submit_url=url, link_type=lt, effort=3,
        required_fields=("display_name", "website", "short_description", "long_description", "categories", "email"),
        tags=("reviews", "b2b", "trust", "llm-cited"), ai_training_signal=True,
        llm_citation_weight=weight,
        notes="AI assistants lean on review aggregators for 'best X' answers. Claim the profile, then earn real reviews.")

# ---------------------------------------------------------------------------
# 5. Startup / product / SaaS listings
# ---------------------------------------------------------------------------
_PRODUCTS = [
    ("product-hunt", "Product Hunt", "producthunt.com", 91, "https://www.producthunt.com/posts/new", 4, "nofollow", 0.5),
    ("betalist", "BetaList", "betalist.com", 79, "https://betalist.com/submit", 3, "dofollow", 0.1),
    ("launching-next", "Launching Next", "launchingnext.com", 62, "https://www.launchingnext.com/submit/", 2, "dofollow", 0.05),
    ("startup-stash", "Startup Stash", "startupstash.com", 72, "https://startupstash.com/add-listing/", 2, "dofollow", 0.1),
    ("saashub", "SaaSHub", "saashub.com", 74, "https://www.saashub.com/submit", 2, "dofollow", 0.2),
    ("saasworthy", "SaaSworthy", "saasworthy.com", 70, "https://www.saasworthy.com/", 3, "nofollow", 0.1),
    ("alternativeto", "AlternativeTo", "alternativeto.net", 85, "https://alternativeto.net/manage/new-app/", 3, "dofollow", 0.4),
    ("slant", "Slant", "slant.co", 68, "https://www.slant.co/", 3, "nofollow", 0.1),
    ("indie-hackers", "Indie Hackers", "indiehackers.com", 83, "https://www.indiehackers.com/products/new", 3, "dofollow", 0.2),
    ("uneed", "Uneed", "uneed.best", 58, "https://www.uneed.best/submit", 2, "dofollow", 0.05),
    ("microlaunch", "MicroLaunch", "microlaunch.net", 52, "https://microlaunch.net/", 2, "dofollow", 0.0),
    ("fazier", "Fazier", "fazier.com", 55, "https://fazier.com/", 2, "dofollow", 0.0),
    ("peerlist", "Peerlist Projects", "peerlist.io", 72, "https://peerlist.io/", 2, "nofollow", 0.05),
    ("startupbase", "StartupBase", "startupbase.io", 57, "https://startupbase.io/", 2, "dofollow", 0.0),
    ("f6s", "F6S", "f6s.com", 81, "https://www.f6s.com/", 3, "nofollow", 0.1),
    ("wellfound", "Wellfound (AngelList Talent)", "wellfound.com", 88, "https://wellfound.com/company/create", 3, "nofollow", 0.2),
    ("crunchbase", "Crunchbase", "crunchbase.com", 92, "https://www.crunchbase.com/add-new", 3, "nofollow", 0.65),
    ("tracxn", "Tracxn", "tracxn.com", 75, "https://tracxn.com/", 3, "nofollow", 0.05),
    ("getlatka", "GetLatka", "getlatka.com", 66, "https://getlatka.com/", 3, "nofollow", 0.05),
    ("toolfinder", "ToolFinder", "toolfinder.co", 60, "https://toolfinder.co/", 2, "dofollow", 0.05),
]
for slug, name, domain, auth, url, effort, lt, weight in _PRODUCTS:
    add(slug, name, domain, "startup_listing", auth, submit_url=url, link_type=lt, effort=effort,
        required_fields=("display_name", "website", "short_description", "long_description", "logo_url", "categories"),
        tags=("product", "saas", "launch"), ai_training_signal=weight > 0.15,
        llm_citation_weight=weight,
        notes="Product listing: ship a real product page, a logo and a 1-line pitch before submitting.")

# ---------------------------------------------------------------------------
# 6. AI tool directories (fast-growing, often dofollow, high GEO value)
# ---------------------------------------------------------------------------
_AI_DIRS = [
    ("theres-an-ai-for-that", "There's An AI For That", "theresanaiforthat.com", 82, "https://theresanaiforthat.com/submit/", 0.3),
    ("futurepedia", "Futurepedia", "futurepedia.io", 79, "https://www.futurepedia.io/submit-tool", 0.25),
    ("futuretools", "Future Tools", "futuretools.io", 74, "https://www.futuretools.io/submit-a-tool", 0.15),
    ("topai-tools", "TopAI.tools", "topai.tools", 68, "https://topai.tools/submit", 0.1),
    ("aitoolnet", "AI Tool Net", "aitoolnet.com", 58, "https://www.aitoolnet.com/submit", 0.05),
    ("insidr-ai", "Insidr AI", "insidr.ai", 62, "https://www.insidr.ai/", 0.05),
    ("aixploria", "Aixploria", "aixploria.com", 64, "https://www.aixploria.com/en/add-ai/", 0.05),
    ("easywithai", "Easy With AI", "easywithai.com", 60, "https://easywithai.com/submit-tool/", 0.05),
    ("openfuture", "OpenFuture AI", "openfuture.ai", 55, "https://openfuture.ai/", 0.0),
    ("aitools-directory", "AI Tools Directory", "aitoolsdirectory.com", 57, "https://aitoolsdirectory.com/submit-tool", 0.0),
]
for slug, name, domain, auth, url, weight in _AI_DIRS:
    add(slug, name, domain, "directory", auth, submit_url=url, link_type="dofollow", effort=2,
        automatable=True, tags=("ai", "tools", "dofollow", "geo"),
        industries=("software", "ai", "saas"), llm_citation_weight=weight,
        notes="Mostly dofollow and fast to approve. Highest-ROI directory tier for software products right now.")

# ---------------------------------------------------------------------------
# 7. Developer platforms & package registries (real dofollow authority)
# ---------------------------------------------------------------------------
_DEV = [
    ("github-profile", "GitHub profile & org", "github.com", 96, "https://github.com/settings/profile", "nofollow", 1, 0.8),
    ("github-pages", "GitHub Pages site", "github.io", 94, "https://pages.github.com/", "dofollow", 3, 0.3),
    ("gitlab-profile", "GitLab profile", "gitlab.com", 93, "https://gitlab.com/-/profile", "nofollow", 1, 0.3),
    ("codeberg", "Codeberg", "codeberg.org", 78, "https://codeberg.org/user/settings", "nofollow", 1, 0.05),
    ("sourceforge", "SourceForge project", "sourceforge.net", 92, "https://sourceforge.net/projects/", "dofollow", 3, 0.2),
    ("bitbucket", "Bitbucket", "bitbucket.org", 91, "https://bitbucket.org/", "nofollow", 1, 0.1),
    ("stackoverflow", "Stack Overflow profile", "stackoverflow.com", 96, "https://stackoverflow.com/users/edit", "nofollow", 1, 0.85),
    ("dev-to", "DEV Community", "dev.to", 90, "https://dev.to/settings/profile", "dofollow", 2, 0.4),
    ("hashnode", "Hashnode", "hashnode.com", 86, "https://hashnode.com/", "dofollow", 2, 0.2),
    ("codepen", "CodePen", "codepen.io", 90, "https://codepen.io/accounts/signup", "nofollow", 2, 0.15),
    ("replit", "Replit", "replit.com", 88, "https://replit.com/", "nofollow", 2, 0.1),
    ("jsfiddle", "JSFiddle", "jsfiddle.net", 84, "https://jsfiddle.net/", "nofollow", 2, 0.05),
    ("observable", "Observable", "observablehq.com", 80, "https://observablehq.com/", "dofollow", 3, 0.05),
    ("huggingface", "Hugging Face", "huggingface.co", 91, "https://huggingface.co/new", "dofollow", 3, 0.45),
    ("kaggle", "Kaggle", "kaggle.com", 92, "https://www.kaggle.com/", "nofollow", 3, 0.3),
    ("npm", "npm package metadata", "npmjs.com", 94, "https://www.npmjs.com/", "nofollow", 2, 0.5),
    ("pypi", "PyPI project metadata", "pypi.org", 94, "https://pypi.org/", "dofollow", 2, 0.5),
    ("packagist", "Packagist", "packagist.org", 87, "https://packagist.org/", "dofollow", 2, 0.15),
    ("crates-io", "crates.io", "crates.io", 88, "https://crates.io/", "dofollow", 2, 0.2),
    ("docker-hub", "Docker Hub", "hub.docker.com", 92, "https://hub.docker.com/", "nofollow", 2, 0.2),
    ("rubygems", "RubyGems", "rubygems.org", 88, "https://rubygems.org/", "dofollow", 2, 0.1),
    ("maven-central", "Maven Central", "central.sonatype.com", 86, "https://central.sonatype.com/", "nofollow", 4, 0.1),
]
for slug, name, domain, auth, url, lt, effort, weight in _DEV:
    add(slug, name, domain, "developer_profile", auth, submit_url=url, link_type=lt, effort=effort,
        required_fields=PROFILE, tags=("developer", "tech", "authority"),
        industries=("software", "saas", "ai", "developer-tools"),
        ai_training_signal=weight >= 0.2, llm_citation_weight=weight,
        notes="Genuinely useful content wins here. Package/repo metadata links are stable and rarely lost.")

# ---------------------------------------------------------------------------
# 8. Brand / social profiles (entity signals more than link equity)
# ---------------------------------------------------------------------------
_SOCIAL = [
    ("linkedin-company", "LinkedIn Company Page", "linkedin.com", 98, "https://www.linkedin.com/company/setup/new/", 0.5),
    ("facebook-page", "Facebook Page", "facebook.com", 96, "https://www.facebook.com/pages/create", 0.2),
    ("x-profile", "X (Twitter) profile", "x.com", 94, "https://x.com/i/flow/signup", 0.25),
    ("instagram", "Instagram business profile", "instagram.com", 94, "https://www.instagram.com/", 0.1),
    ("youtube-channel", "YouTube channel", "youtube.com", 100, "https://www.youtube.com/", 0.6),
    ("pinterest", "Pinterest business", "pinterest.com", 94, "https://www.pinterest.com/business/create/", 0.1),
    ("tiktok-business", "TikTok business profile", "tiktok.com", 95, "https://www.tiktok.com/business/", 0.05),
    ("reddit-profile", "Reddit profile", "reddit.com", 96, "https://www.reddit.com/settings/profile", 0.9),
    ("tumblr", "Tumblr blog", "tumblr.com", 92, "https://www.tumblr.com/register", 0.05),
    ("medium", "Medium publication", "medium.com", 94, "https://medium.com/new-story", 0.35),
    ("substack", "Substack newsletter", "substack.com", 90, "https://substack.com/", 0.2),
    ("behance", "Behance", "behance.net", 91, "https://www.behance.net/", 0.05),
    ("dribbble", "Dribbble", "dribbble.com", 90, "https://dribbble.com/", 0.05),
    ("vimeo", "Vimeo", "vimeo.com", 93, "https://vimeo.com/join", 0.05),
    ("slideshare", "SlideShare", "slideshare.net", 91, "https://www.slideshare.net/", 0.1),
    ("issuu", "Issuu", "issuu.com", 88, "https://issuu.com/", 0.05),
    ("scribd", "Scribd", "scribd.com", 90, "https://www.scribd.com/", 0.1),
    ("flickr", "Flickr", "flickr.com", 91, "https://www.flickr.com/", 0.05),
    ("soundcloud", "SoundCloud", "soundcloud.com", 91, "https://soundcloud.com/", 0.05),
    ("gravatar", "Gravatar profile", "gravatar.com", 88, "https://gravatar.com/", 0.05),
    ("about-me", "About.me", "about.me", 80, "https://about.me/", 0.02),
    ("linktree", "Linktree", "linktr.ee", 85, "https://linktr.ee/", 0.02),
    ("notion-site", "Notion public site", "notion.site", 86, "https://www.notion.so/", 0.05),
    ("mastodon", "Mastodon profile", "mastodon.social", 82, "https://mastodon.social/", 0.05),
    ("bluesky", "Bluesky profile", "bsky.app", 80, "https://bsky.app/", 0.05),
]
for slug, name, domain, auth, url, weight in _SOCIAL:
    add(slug, name, domain, "social_profile", auth, submit_url=url, link_type="nofollow", effort=2,
        required_fields=PROFILE, tags=("brand", "entity", "social"),
        ai_training_signal=weight >= 0.2, llm_citation_weight=weight,
        notes="Treat as entity/brand signals: consistent name, logo, description and website field everywhere.")

# ---------------------------------------------------------------------------
# 9. Q&A, forums and communities (participation, never drive-by dropping)
# ---------------------------------------------------------------------------
_QA = [
    ("quora", "Quora", "quora.com", 92, "https://www.quora.com/", 4, 0.7),
    ("stackexchange", "Stack Exchange network", "stackexchange.com", 93, "https://stackexchange.com/", 4, 0.6),
    ("hacker-news", "Hacker News", "news.ycombinator.com", 91, "https://news.ycombinator.com/submit", 3, 0.5),
    ("lobsters", "Lobste.rs", "lobste.rs", 74, "https://lobste.rs/", 4, 0.1),
    ("growthhackers", "GrowthHackers", "growthhackers.com", 76, "https://growthhackers.com/", 3, 0.05),
    ("designer-news", "Designer News", "designernews.co", 73, "https://www.designernews.co/", 3, 0.05),
    ("discourse-meta", "Discourse Meta", "meta.discourse.org", 80, "https://meta.discourse.org/", 4, 0.1),
    ("warrior-forum", "Warrior Forum", "warriorforum.com", 72, "https://www.warriorforum.com/", 4, 0.05),
    ("reddit-communities", "Reddit topical communities", "reddit.com", 96, "https://www.reddit.com/", 4, 0.9),
]
for slug, name, domain, auth, url, effort, weight in _QA:
    add(slug, name, domain, "qa_community", auth, submit_url=url, link_type="nofollow", effort=effort,
        required_fields=("display_name", "website"), tags=("community", "participation", "llm-cited"),
        ai_training_signal=True, llm_citation_weight=weight,
        guidelines_url="https://www.reddit.com/wiki/selfpromotion" if "reddit" in domain else "",
        notes="Earn standing first. Reddit and Stack Exchange are the two corpora LLMs quote most - a genuinely "
              "helpful answer that happens to cite you is worth more than fifty directory links.")

# ---------------------------------------------------------------------------
# 10. Knowledge graph / open data (the strongest AI-visibility lever)
# ---------------------------------------------------------------------------
add("wikidata", "Wikidata item", "wikidata.org", "wiki", 95,
    submit_url="https://www.wikidata.org/wiki/Special:NewItem", link_type="dofollow", effort=4,
    required_fields=("legal_name", "website", "founded_year", "country", "short_description"),
    tags=("knowledge-graph", "entity", "open-data", "geo"), ai_training_signal=True,
    llm_citation_weight=0.7, guidelines_url="https://www.wikidata.org/wiki/Wikidata:Notability",
    notes="The single highest-leverage entity asset. Needs verifiable third-party references - build those FIRST, "
          "then create the item. Do not create an item for a non-notable entity; it will be deleted.")
add("wikipedia", "Wikipedia article", "wikipedia.org", "wiki", 100,
    submit_url="https://en.wikipedia.org/wiki/Wikipedia:Articles_for_creation", link_type="nofollow", effort=5,
    required_fields=("legal_name", "website", "founded_year"),
    tags=("knowledge-graph", "entity", "geo", "high-risk"), ai_training_signal=True,
    llm_citation_weight=0.95, guidelines_url="https://en.wikipedia.org/wiki/Wikipedia:Notability_(organizations_and_companies)",
    requires_moderation=True,
    notes="Do NOT self-create. Only viable once independent, significant press coverage exists; paid or undisclosed "
          "editing is against policy and backfires. Track notability progress here, act via disclosed request only.")
add("dbpedia", "DBpedia (derived from Wikipedia)", "dbpedia.org", "ai_dataset", 88,
    submit_url="https://www.dbpedia.org/", link_type="dofollow", effort=5,
    tags=("knowledge-graph", "open-data"), ai_training_signal=True, llm_citation_weight=0.3,
    notes="Not directly editable - it mirrors Wikipedia/Wikidata. Listed so the dependency is explicit.")
add("wikivoyage", "Wikivoyage listing", "wikivoyage.org", "wiki", 84,
    submit_url="https://en.wikivoyage.org/", link_type="dofollow", effort=4, required_fields=NAP,
    industries=("travel", "hospitality", "restaurant", "tourism"),
    tags=("knowledge-graph", "travel"), ai_training_signal=True, llm_citation_weight=0.2,
    notes="Legitimate for real travel/hospitality venues only. Follow the listing template exactly.")
add("fandom", "Fandom wiki", "fandom.com", "wiki", 91,
    submit_url="https://www.fandom.com/", link_type="nofollow", effort=4,
    tags=("wiki", "niche"), ai_training_signal=True, llm_citation_weight=0.25,
    notes="Only where a genuine topical wiki exists for your niche.")

# ---------------------------------------------------------------------------
# 11. Self-published content platforms (content distribution + links)
# ---------------------------------------------------------------------------
_BLOGS = [
    ("blogger", "Blogger", "blogspot.com", 92, "https://www.blogger.com/", "nofollow", 3),
    ("wordpress-com", "WordPress.com", "wordpress.com", 94, "https://wordpress.com/start", "nofollow", 3),
    ("ghost-io", "Ghost publication", "ghost.io", 86, "https://ghost.org/", "dofollow", 3),
    ("write-as", "Write.as", "write.as", 74, "https://write.as/", "dofollow", 2),
    ("bear-blog", "Bear Blog", "bearblog.dev", 70, "https://bearblog.dev/", "dofollow", 2),
    ("telegraph", "Telegra.ph", "telegra.ph", 82, "https://telegra.ph/", "dofollow", 1),
    ("linkedin-articles", "LinkedIn Articles", "linkedin.com", 98, "https://www.linkedin.com/", "nofollow", 3),
    ("weebly", "Weebly site", "weebly.com", 88, "https://www.weebly.com/", "nofollow", 3),
    ("site123", "SITE123", "site123.com", 76, "https://www.site123.com/", "nofollow", 3),
    ("strikingly", "Strikingly", "strikingly.com", 82, "https://www.strikingly.com/", "nofollow", 3),
]
for slug, name, domain, auth, url, lt, effort in _BLOGS:
    add(slug, name, domain, "blog_platform", auth, submit_url=url, link_type=lt, effort=effort,
        required_fields=("display_name", "website", "short_description"),
        tags=("content", "distribution"), llm_citation_weight=0.1,
        notes="Publish genuinely distinct content (a case study, a dataset, a tutorial) - never spun duplicates of "
              "your own pages, which is what turns this tactic into a liability.")

# ---------------------------------------------------------------------------
# 12. Press release distribution with usable free tiers
# ---------------------------------------------------------------------------
_PR = [
    ("prlog", "PRLog", "prlog.org", 78, "https://www.prlog.org/pub/", "dofollow", True),
    ("openpr", "OpenPR", "openpr.com", 76, "https://www.openpr.com/news/submit.html", "dofollow", True),
    ("issuewire", "IssueWire", "issuewire.com", 70, "https://www.issuewire.com/", "nofollow", True),
    ("pr-com", "PR.com", "pr.com", 72, "https://www.pr.com/", "nofollow", True),
    ("1888pressrelease", "1888PressRelease", "1888pressrelease.com", 66, "https://www.1888pressrelease.com/", "dofollow", True),
    ("pressreleasepoint", "PressReleasePoint", "pressreleasepoint.com", 62, "https://www.pressreleasepoint.com/", "dofollow", True),
]
for slug, name, domain, auth, url, lt, free in _PR:
    add(slug, name, domain, "press_release", auth, submit_url=url, link_type=lt, is_free=free, effort=3,
        required_fields=("display_name", "website", "short_description", "long_description", "email", "city", "country"),
        tags=("pr", "announcement"), llm_citation_weight=0.05,
        notes="Use for genuine news only (launch, funding, partnership, data study). Syndicated PR links carry little "
              "ranking weight on their own - the value is journalists discovering the story.")

# ---------------------------------------------------------------------------
# 13. Podcast / media directories
# ---------------------------------------------------------------------------
_PODCAST = [
    ("apple-podcasts", "Apple Podcasts", "podcasts.apple.com", 96, "https://podcastsconnect.apple.com/", 0.2),
    ("spotify-podcasters", "Spotify for Creators", "spotify.com", 95, "https://creators.spotify.com/", 0.15),
    ("podchaser", "Podchaser", "podchaser.com", 82, "https://www.podchaser.com/", 0.1),
    ("listen-notes", "Listen Notes", "listennotes.com", 80, "https://www.listennotes.com/submit/", 0.1),
    ("podcast-index", "Podcast Index", "podcastindex.org", 72, "https://podcastindex.org/add", 0.05),
    ("player-fm", "Player FM", "player.fm", 78, "https://player.fm/", 0.05),
]
for slug, name, domain, auth, url, weight in _PODCAST:
    add(slug, name, domain, "podcast", auth, submit_url=url, link_type="dofollow", effort=3,
        required_fields=("display_name", "website", "short_description", "logo_url"),
        tags=("podcast", "media"), llm_citation_weight=weight,
        notes="Either list your own show, or use guest appearances - show notes links are durable and contextual.")

# ---------------------------------------------------------------------------
# 14. Content / RSS aggregators
# ---------------------------------------------------------------------------
_AGG = [
    ("feedspot", "Feedspot", "feedspot.com", 78, "https://www.feedspot.com/", "nofollow"),
    ("blogarama", "Blogarama", "blogarama.com", 66, "https://www.blogarama.com/add-blog", "dofollow"),
    ("bloglovin", "Bloglovin'", "bloglovin.com", 79, "https://www.bloglovin.com/", "nofollow"),
    ("alltop", "Alltop", "alltop.com", 70, "https://alltop.com/", "dofollow"),
    ("feedly", "Feedly", "feedly.com", 89, "https://feedly.com/", "nofollow"),
    ("flipboard", "Flipboard magazine", "flipboard.com", 91, "https://flipboard.com/", "nofollow"),
]
for slug, name, domain, auth, url, lt in _AGG:
    add(slug, name, domain, "aggregator", auth, submit_url=url, link_type=lt, effort=2, automatable=True,
        required_fields=("display_name", "website", "short_description"),
        tags=("rss", "distribution"), llm_citation_weight=0.05,
        notes="Cheap distribution for a blog that actually publishes on a schedule.")

# ---------------------------------------------------------------------------
# 15. Tactic templates - prospected at runtime, not a fixed destination
# ---------------------------------------------------------------------------
add("resource-page-prospecting", "Resource page link building", "*", "resource_page", 0,
    submit_url="", link_type="dofollow", effort=4, automatable=False, requires_account=False,
    required_fields=("display_name", "website", "short_description"),
    tags=("tactic", "prospecting", "outreach"),
    notes="Search intitle:\"resources\" + topic, qualify pages that already link out, pitch one genuinely useful asset. "
          "Prospected by the opportunity engine from competitor link intersects.")
add("broken-link-building", "Broken link building", "*", "resource_page", 0,
    effort=4, link_type="dofollow", requires_account=False,
    tags=("tactic", "prospecting", "outreach"),
    notes="Find 404s on relevant pages (crawler reports them), publish a replacement, tell the maintainer. "
          "High conversion because you are fixing their problem.")
add("unlinked-mention-reclamation", "Unlinked brand mention reclamation", "*", "resource_page", 0,
    effort=2, link_type="dofollow", requires_account=False,
    tags=("tactic", "reclamation", "fastest-win"),
    notes="Highest conversion rate of any tactic: someone already named you, just ask for the link. "
          "Run the mentions monitor, then the one-line reclamation template.")
add("guest-post-outreach", "Guest posting / contributed articles", "*", "guest_post", 0,
    effort=5, link_type="dofollow", requires_account=False,
    tags=("tactic", "content", "outreach"),
    notes="Only on sites with real editorial standards and real readers. Never pay for placement on a link farm - "
          "that is exactly the footprint manual actions look for.")
add("digital-pr-data-study", "Digital PR / original data study", "*", "press_release", 0,
    effort=5, link_type="dofollow", requires_account=False,
    tags=("tactic", "content", "authority", "highest-roi"),
    notes="The only tactic that reliably earns links from sites you cannot submit to. One original dataset or survey "
          "per quarter beats a year of directory submissions.")
add("supplier-partner-customer-links", "Supplier / partner / customer pages", "*", "resource_page", 0,
    effort=2, link_type="dofollow", requires_account=False,
    tags=("tactic", "relationship", "fastest-win"),
    notes="Existing commercial relationships are the most under-used link source: partner pages, 'built with', "
          "case studies, integration listings, testimonials.")
add("scholarship-community-sponsorship", "Local sponsorship & community pages", "*", "edu_gov", 0,
    effort=4, link_type="dofollow", requires_account=False,
    tags=("tactic", "local", "sponsorship"),
    notes="Real sponsorships of local clubs/events/charities earn genuine .org and local-press links. "
          "Avoid mass 'scholarship link' schemes - they are a known spam pattern.")
add("chamber-of-commerce-local", "Local chamber of commerce / trade body", "*", "edu_gov", 0,
    effort=3, link_type="dofollow", requires_account=True, required_fields=NAP,
    tags=("tactic", "local", "membership"),
    notes="Paid membership usually includes a dofollow member listing on a genuinely authoritative local domain.")
add("hark-journalist-requests", "Journalist request platforms (HARO-style)", "*", "guest_post", 0,
    effort=3, link_type="dofollow", requires_account=True,
    tags=("tactic", "pr", "expert-quote"),
    notes="Answer reporter queries (Featured, Qwoted, SourceBottle, #JournoRequest). Slow but earns real editorial links.")


# ---------------------------------------------------------------------------
# 16. Country directories - UK / IE
# ---------------------------------------------------------------------------
_UK = [
    ("yell", "Yell.com", "yell.com", 84, "https://www.yell.com/", "nofollow"),
    ("thomson-local", "Thomson Local", "thomsonlocal.com", 71, "https://www.thomsonlocal.com/", "dofollow"),
    ("freeindex", "FreeIndex", "freeindex.co.uk", 69, "https://www.freeindex.co.uk/", "dofollow"),
    ("scoot", "Scoot", "scoot.co.uk", 66, "https://www.scoot.co.uk/", "nofollow"),
    ("cylex-uk", "Cylex UK", "cylex-uk.co.uk", 60, "https://www.cylex-uk.co.uk/", "dofollow"),
    ("192-com", "192.com", "192.com", 72, "https://www.192.com/", "nofollow"),
    ("approved-business", "Approved Business", "approvedbusiness.co.uk", 58, "https://www.approvedbusiness.co.uk/", "dofollow"),
    ("applegate", "Applegate Marketplace", "applegate.co.uk", 64, "https://www.applegate.co.uk/", "dofollow"),
    ("the-best-of", "TheBestOf", "thebestof.co.uk", 62, "https://www.thebestof.co.uk/", "dofollow"),
    ("checkatrade", "Checkatrade", "checkatrade.com", 78, "https://www.checkatrade.com/", "nofollow"),
    ("mybuilder", "MyBuilder", "mybuilder.com", 74, "https://www.mybuilder.com/", "nofollow"),
    ("goldenpages-ie", "Golden Pages (IE)", "goldenpages.ie", 63, "https://www.goldenpages.ie/", "nofollow"),
]
for slug, name, domain, auth, url, lt in _UK:
    add(slug, name, domain, "local_citation", auth, submit_url=url, link_type=lt, effort=2,
        required_fields=NAP, countries=("GB", "IE"), languages=("en",),
        tags=("local", "citation", "uk"), automatable=True)

# ---------------------------------------------------------------------------
# 17. Country directories - DE / AT / CH
# ---------------------------------------------------------------------------
_DE = [
    ("das-telefonbuch", "Das Telefonbuch", "dastelefonbuch.de", 78, "https://www.dastelefonbuch.de/", "nofollow"),
    ("gelbeseiten", "Gelbe Seiten", "gelbeseiten.de", 80, "https://www.gelbeseiten.de/", "nofollow"),
    ("11880", "11880.com", "11880.com", 73, "https://www.11880.com/", "nofollow"),
    ("meinestadt", "meinestadt.de", "meinestadt.de", 76, "https://www.meinestadt.de/", "dofollow"),
    ("golocal-de", "GoLocal", "golocal.de", 65, "https://www.golocal.de/", "dofollow"),
    ("stadtbranchenbuch", "Stadtbranchenbuch", "stadtbranchenbuch.com", 62, "https://www.stadtbranchenbuch.com/", "dofollow"),
    ("wlw", "wlw (Wer liefert was)", "wlw.de", 77, "https://www.wlw.de/", "nofollow"),
    ("firmenwissen", "FirmenWissen", "firmenwissen.de", 70, "https://www.firmenwissen.de/", "nofollow"),
    ("cylex-de", "Cylex Deutschland", "cylex.de", 61, "https://www.cylex.de/", "dofollow"),
    ("kennstdueinen", "kennstdueinen.de", "kennstdueinen.de", 57, "https://www.kennstdueinen.de/", "dofollow"),
    ("herold-at", "Herold (AT)", "herold.at", 72, "https://www.herold.at/", "nofollow"),
    ("local-ch", "local.ch", "local.ch", 74, "https://www.local.ch/", "nofollow"),
]
for slug, name, domain, auth, url, lt in _DE:
    add(slug, name, domain, "local_citation", auth, submit_url=url, link_type=lt, effort=2,
        required_fields=NAP, countries=("DE", "AT", "CH"), languages=("de",),
        tags=("local", "citation", "dach"), automatable=True)

# ---------------------------------------------------------------------------
# 18. Country directories - FR / IT / NL / PT / NORDICS
# ---------------------------------------------------------------------------
_EU = [
    ("pagesjaunes", "PagesJaunes", "pagesjaunes.fr", 82, "https://www.pagesjaunes.fr/", ("FR",), ("fr",)),
    ("societe-com", "Societe.com", "societe.com", 80, "https://www.societe.com/", ("FR",), ("fr",)),
    ("kompass", "Kompass B2B", "kompass.com", 78, "https://www.kompass.com/", ("FR", "*"), ("fr", "en")),
    ("annuaire-horaire", "Annuaire Horaire", "annuaire-horaire.fr", 58, "https://www.annuaire-horaire.fr/", ("FR",), ("fr",)),
    ("cylex-fr", "Cylex France", "cylex-france.fr", 58, "https://www.cylex-france.fr/", ("FR",), ("fr",)),
    ("paginegialle", "PagineGialle", "paginegialle.it", 79, "https://www.paginegialle.it/", ("IT",), ("it",)),
    ("paginebianche", "PagineBianche", "paginebianche.it", 76, "https://www.paginebianche.it/", ("IT",), ("it",)),
    ("misterimprese", "Misterimprese", "misterimprese.it", 60, "https://www.misterimprese.it/", ("IT",), ("it",)),
    ("virgilio-local", "Virgilio Local", "virgilio.it", 81, "https://local.virgilio.it/", ("IT",), ("it",)),
    ("detelefoongids", "De Telefoongids", "detelefoongids.nl", 72, "https://www.detelefoongids.nl/", ("NL",), ("nl",)),
    ("openingstijden", "Openingstijden.nl", "openingstijden.nl", 63, "https://www.openingstijden.nl/", ("NL",), ("nl",)),
    ("cylex-nl", "Cylex Nederland", "cylex.nl", 57, "https://www.cylex.nl/", ("NL",), ("nl",)),
    ("pai-pt", "PAI Portugal", "pai.pt", 68, "https://www.pai.pt/", ("PT",), ("pt",)),
    ("hitta-se", "Hitta.se", "hitta.se", 75, "https://www.hitta.se/", ("SE",), ("sv",)),
    ("krak-dk", "Krak", "krak.dk", 73, "https://www.krak.dk/", ("DK",), ("da",)),
    ("gulesider-no", "Gule Sider", "gulesider.no", 74, "https://www.gulesider.no/", ("NO",), ("no",)),
    ("yritystele-fi", "Yritystele", "yritystele.fi", 62, "https://www.yritystele.fi/", ("FI",), ("fi",)),
    ("panoramafirm-pl", "Panorama Firm", "panoramafirm.pl", 70, "https://panoramafirm.pl/", ("PL",), ("pl",)),
]
for slug, name, domain, auth, url, countries, languages in _EU:
    add(slug, name, domain, "local_citation", auth, submit_url=url, link_type="nofollow", effort=2,
        required_fields=NAP, countries=countries, languages=languages,
        tags=("local", "citation", "europe"), automatable=True)

# ---------------------------------------------------------------------------
# 19. Country directories - Americas / APAC
# ---------------------------------------------------------------------------
_WORLD = [
    ("yellowpages-ca", "YellowPages.ca", "yellowpages.ca", 82, "https://www.yellowpages.ca/", ("CA",), ("en", "fr")),
    ("canpages", "Canpages", "canpages.ca", 66, "https://www.canpages.ca/", ("CA",), ("en",)),
    ("profile-canada", "Profile Canada", "profilecanada.com", 60, "https://profilecanada.com/", ("CA",), ("en",)),
    ("yellowpages-au", "Yellow Pages Australia", "yellowpages.com.au", 80, "https://www.yellowpages.com.au/", ("AU",), ("en",)),
    ("truelocal", "TrueLocal", "truelocal.com.au", 71, "https://www.truelocal.com.au/", ("AU",), ("en",)),
    ("startlocal", "StartLocal", "startlocal.com.au", 62, "https://www.startlocal.com.au/", ("AU",), ("en",)),
    ("localsearch-au", "Localsearch", "localsearch.com.au", 68, "https://www.localsearch.com.au/", ("AU",), ("en",)),
    ("finda-nz", "Finda NZ", "finda.co.nz", 58, "https://www.finda.co.nz/", ("NZ",), ("en",)),
    ("justdial", "JustDial", "justdial.com", 80, "https://www.justdial.com/", ("IN",), ("en", "hi")),
    ("sulekha", "Sulekha", "sulekha.com", 74, "https://www.sulekha.com/", ("IN",), ("en",)),
    ("indiamart", "IndiaMART", "indiamart.com", 85, "https://www.indiamart.com/", ("IN",), ("en",)),
    ("tradeindia", "TradeIndia", "tradeindia.com", 76, "https://www.tradeindia.com/", ("IN",), ("en",)),
    ("telelistas", "Telelistas", "telelistas.net", 66, "https://www.telelistas.net/", ("BR",), ("pt",)),
    ("apontador", "Apontador", "apontador.com.br", 68, "https://www.apontador.com.br/", ("BR",), ("pt",)),
    ("guiamais", "GuiaMais", "guiamais.com.br", 70, "https://www.guiamais.com.br/", ("BR",), ("pt",)),
    ("encuentra24", "Encuentra24", "encuentra24.com", 68, "https://www.encuentra24.com/", ("PA", "CR", "SV", "NI", "GT"), ("es",)),
    ("locanto", "Locanto", "locanto.com", 72, "https://www.locanto.com/", ("*",), ("es", "en", "de")),
    ("vulka", "Vulka", "vulka.es", 52, "https://www.vulka.es/", ("ES", "MX", "AR"), ("es",)),
    ("emol-clasificados", "Yapo / clasificados CL", "yapo.cl", 70, "https://www.yapo.cl/", ("CL",), ("es",)),
    ("paginas-amarillas-pe", "Páginas Amarillas Perú", "paginasamarillas.com.pe", 58, "https://www.paginasamarillas.com.pe/", ("PE",), ("es",)),
]
for slug, name, domain, auth, url, countries, languages in _WORLD:
    add(slug, name, domain, "local_citation", auth, submit_url=url, link_type="nofollow", effort=2,
        required_fields=NAP, countries=countries, languages=languages,
        tags=("local", "citation"), automatable=True)

# ---------------------------------------------------------------------------
# 20. Integration marketplaces & app stores - strong, durable dofollow links
# ---------------------------------------------------------------------------
_MARKETPLACES = [
    ("zapier-apps", "Zapier App Directory", "zapier.com", 92, "https://zapier.com/developer", 4, "dofollow", 0.3),
    ("make-apps", "Make (Integromat) apps", "make.com", 86, "https://www.make.com/en/developers", 4, "dofollow", 0.1),
    ("slack-marketplace", "Slack App Directory", "slack.com", 94, "https://api.slack.com/apps", 4, "nofollow", 0.15),
    ("shopify-app-store", "Shopify App Store", "apps.shopify.com", 92, "https://partners.shopify.com/", 5, "dofollow", 0.25),
    ("wordpress-plugins", "WordPress.org plugin directory", "wordpress.org", 96, "https://wordpress.org/plugins/developers/add/", 5, "dofollow", 0.4),
    ("wordpress-themes", "WordPress.org theme directory", "wordpress.org", 96, "https://wordpress.org/themes/upload/", 5, "dofollow", 0.2),
    ("chrome-web-store", "Chrome Web Store", "chromewebstore.google.com", 95, "https://chrome.google.com/webstore/devconsole", 4, "nofollow", 0.2),
    ("firefox-addons", "Firefox Add-ons", "addons.mozilla.org", 93, "https://addons.mozilla.org/developers/", 4, "dofollow", 0.15),
    ("vscode-marketplace", "VS Code Marketplace", "marketplace.visualstudio.com", 92, "https://marketplace.visualstudio.com/manage", 4, "nofollow", 0.2),
    ("jetbrains-marketplace", "JetBrains Marketplace", "plugins.jetbrains.com", 88, "https://plugins.jetbrains.com/", 4, "dofollow", 0.1),
    ("atlassian-marketplace", "Atlassian Marketplace", "marketplace.atlassian.com", 89, "https://marketplace.atlassian.com/", 5, "nofollow", 0.1),
    ("hubspot-marketplace", "HubSpot App Marketplace", "ecosystem.hubspot.com", 88, "https://ecosystem.hubspot.com/marketplace/apps", 4, "dofollow", 0.15),
    ("salesforce-appexchange", "Salesforce AppExchange", "appexchange.salesforce.com", 90, "https://appexchange.salesforce.com/", 5, "nofollow", 0.1),
    ("microsoft-appsource", "Microsoft AppSource", "appsource.microsoft.com", 91, "https://appsource.microsoft.com/", 5, "nofollow", 0.1),
    ("aws-marketplace", "AWS Marketplace", "aws.amazon.com", 96, "https://aws.amazon.com/marketplace/management/", 5, "nofollow", 0.15),
    ("figma-community", "Figma Community", "figma.com", 92, "https://www.figma.com/community", 3, "nofollow", 0.1),
    ("notion-templates", "Notion Template Gallery", "notion.com", 90, "https://www.notion.com/templates", 3, "nofollow", 0.05),
    ("openai-gpt-store", "OpenAI GPT Store", "chatgpt.com", 95, "https://chatgpt.com/gpts", 3, "nofollow", 0.1),
    ("mcp-registry", "MCP server registries", "github.com", 96, "https://github.com/modelcontextprotocol/servers", 3, "dofollow", 0.2),
    ("awesome-lists", "GitHub 'awesome-*' lists", "github.com", 96, "https://github.com/sindresorhus/awesome", 3, "dofollow", 0.35),
]
for slug, name, domain, auth, url, effort, lt, weight in _MARKETPLACES:
    add(slug, name, domain, "product_listing", auth, submit_url=url, link_type=lt, effort=effort,
        required_fields=("display_name", "website", "short_description", "long_description", "logo_url"),
        tags=("marketplace", "integration", "durable"), industries=("software", "saas", "ai"),
        ai_training_signal=weight >= 0.2, llm_citation_weight=weight,
        notes="Integration/app listings are among the most durable link assets available: relevant, rarely removed, "
              "and they bring qualified traffic rather than just equity.")

# ---------------------------------------------------------------------------
# 21. Academic / research / dataset platforms (very high LLM grounding value)
# ---------------------------------------------------------------------------
_RESEARCH = [
    ("arxiv", "arXiv preprint", "arxiv.org", 95, "https://arxiv.org/submit", 5, "dofollow", 0.7),
    ("ssrn", "SSRN", "ssrn.com", 88, "https://www.ssrn.com/", 5, "nofollow", 0.3),
    ("researchgate", "ResearchGate", "researchgate.net", 92, "https://www.researchgate.net/", 3, "nofollow", 0.4),
    ("orcid", "ORCID record", "orcid.org", 90, "https://orcid.org/register", 2, "dofollow", 0.2),
    ("semantic-scholar", "Semantic Scholar", "semanticscholar.org", 89, "https://www.semanticscholar.org/", 3, "nofollow", 0.35),
    ("google-scholar", "Google Scholar profile", "scholar.google.com", 96, "https://scholar.google.com/citations", 3, "nofollow", 0.3),
    ("zenodo", "Zenodo dataset/DOI", "zenodo.org", 88, "https://zenodo.org/uploads/new", 3, "dofollow", 0.3),
    ("figshare", "Figshare", "figshare.com", 85, "https://figshare.com/", 3, "dofollow", 0.2),
    ("osf", "Open Science Framework", "osf.io", 84, "https://osf.io/", 3, "dofollow", 0.2),
    ("papers-with-code", "Papers with Code", "paperswithcode.com", 86, "https://paperswithcode.com/", 4, "dofollow", 0.3),
    ("data-world", "data.world", "data.world", 80, "https://data.world/", 3, "dofollow", 0.15),
    ("kaggle-datasets", "Kaggle Datasets", "kaggle.com", 92, "https://www.kaggle.com/datasets", 3, "nofollow", 0.35),
    ("huggingface-datasets", "Hugging Face Datasets", "huggingface.co", 91, "https://huggingface.co/new-dataset", 3, "dofollow", 0.4),
]
for slug, name, domain, auth, url, effort, lt, weight in _RESEARCH:
    add(slug, name, domain, "ai_dataset", auth, submit_url=url, link_type=lt, effort=effort,
        required_fields=("display_name", "website", "long_description"),
        tags=("research", "dataset", "geo", "citable"), ai_training_signal=True, llm_citation_weight=weight,
        notes="If you publish an original dataset or methodology, this tier makes it citable by both researchers and "
              "LLMs. Highest-leverage group for AI visibility after Wikipedia/Wikidata.")

# ---------------------------------------------------------------------------
# 22. Vertical directories - hospitality, health, legal, home, property, travel
# ---------------------------------------------------------------------------
_VERTICAL = [
    ("tripadvisor", "Tripadvisor", "tripadvisor.com", 94, ("travel", "restaurant", "hospitality"), 0.45),
    ("opentable", "OpenTable", "opentable.com", 88, ("restaurant",), 0.2),
    ("thefork", "TheFork", "thefork.com", 84, ("restaurant",), 0.1),
    ("zomato", "Zomato", "zomato.com", 87, ("restaurant",), 0.15),
    ("restaurant-guru", "Restaurant Guru", "restaurantguru.com", 74, ("restaurant",), 0.1),
    ("happycow", "HappyCow", "happycow.net", 78, ("restaurant", "vegan"), 0.1),
    ("booking", "Booking.com", "booking.com", 95, ("hotel", "travel"), 0.3),
    ("hostelworld", "Hostelworld", "hostelworld.com", 84, ("hotel", "travel"), 0.1),
    ("getyourguide", "GetYourGuide", "getyourguide.com", 87, ("travel", "tours"), 0.15),
    ("viator", "Viator", "viator.com", 88, ("travel", "tours"), 0.15),
    ("healthgrades", "Healthgrades", "healthgrades.com", 88, ("health", "medical"), 0.3),
    ("zocdoc", "Zocdoc", "zocdoc.com", 85, ("health", "medical"), 0.2),
    ("vitals", "Vitals", "vitals.com", 80, ("health", "medical"), 0.1),
    ("ratemds", "RateMDs", "ratemds.com", 78, ("health", "medical"), 0.1),
    ("doctoralia", "Doctoralia", "doctoralia.es", 82, ("health", "medical"), 0.15),
    ("topdoctors", "Top Doctors", "topdoctors.es", 74, ("health", "medical"), 0.05),
    ("avvo", "Avvo", "avvo.com", 85, ("legal",), 0.25),
    ("justia", "Justia Lawyer Directory", "justia.com", 89, ("legal",), 0.3),
    ("findlaw", "FindLaw", "findlaw.com", 88, ("legal",), 0.25),
    ("martindale", "Martindale-Hubbell", "martindale.com", 82, ("legal",), 0.15),
    ("angi", "Angi", "angi.com", 87, ("home-services",), 0.2),
    ("thumbtack", "Thumbtack", "thumbtack.com", 86, ("home-services",), 0.15),
    ("houzz", "Houzz", "houzz.com", 90, ("home-services", "interior-design"), 0.2),
    ("porch", "Porch", "porch.com", 78, ("home-services",), 0.05),
    ("bark", "Bark", "bark.com", 80, ("home-services",), 0.05),
    ("zillow-pro", "Zillow professional", "zillow.com", 93, ("real-estate",), 0.25),
    ("realtor-com", "Realtor.com", "realtor.com", 92, ("real-estate",), 0.25),
    ("idealista", "Idealista", "idealista.com", 86, ("real-estate",), 0.15),
    ("fotocasa", "Fotocasa", "fotocasa.es", 82, ("real-estate",), 0.1),
    ("repairpal", "RepairPal", "repairpal.com", 78, ("automotive",), 0.1),
    ("cars-com-dealers", "Cars.com dealer listing", "cars.com", 88, ("automotive",), 0.1),
    ("guidestar", "Candid / GuideStar", "candid.org", 84, ("nonprofit",), 0.2),
    ("globalgiving", "GlobalGiving", "globalgiving.org", 82, ("nonprofit",), 0.1),
    ("eventbrite", "Eventbrite organiser page", "eventbrite.com", 92, ("events",), 0.15),
    ("meetup", "Meetup group", "meetup.com", 91, ("events", "community"), 0.15),
    ("class-central", "Class Central", "classcentral.com", 82, ("education",), 0.15),
    ("coursereport", "Course Report", "coursereport.com", 72, ("education",), 0.05),
]
for slug, name, domain, auth, industries, weight in _VERTICAL:
    add(slug, name, domain, "directory", auth, submit_url=f"https://{domain}", link_type="nofollow", effort=3,
        required_fields=NAP, industries=industries, tags=("vertical", "industry") + industries,
        ai_training_signal=weight >= 0.2, llm_citation_weight=weight,
        notes="Vertical directories outrank generic ones for relevance and referral traffic. Only list if you genuinely "
              "operate in this category.")

# ---------------------------------------------------------------------------
# 23. Social bookmarking / curation - low value, included with an honest label
# ---------------------------------------------------------------------------
_BOOKMARK = [
    ("diigo", "Diigo", "diigo.com", 80),
    ("raindrop", "Raindrop.io", "raindrop.io", 78),
    ("pearltrees", "Pearltrees", "pearltrees.com", 74),
    ("mix", "Mix", "mix.com", 76),
    ("folkd", "Folkd", "folkd.com", 62),
    ("scoop-it", "Scoop.it", "scoop.it", 79),
    ("pocket", "Pocket", "getpocket.com", 88),
    ("digg", "Digg", "digg.com", 85),
]
for slug, name, domain, auth in _BOOKMARK:
    add(slug, name, domain, "aggregator", auth, submit_url=f"https://{domain}", link_type="nofollow",
        effort=1, automatable=True, required_fields=("display_name", "website"),
        tags=("bookmarking", "low-value"), llm_citation_weight=0.0,
        notes="LOW VALUE - nofollow, minimal ranking effect. Kept only for indexation/discovery of new pages. "
              "Do not build a strategy on this tier.")

# ---------------------------------------------------------------------------
# 24. Product-community forums where vendors legitimately participate
# ---------------------------------------------------------------------------
_FORUMS = [
    ("wordpress-support", "WordPress.org support forums", "wordpress.org", 96, 0.3),
    ("shopify-community", "Shopify Community", "community.shopify.com", 90, 0.15),
    ("salesforce-trailblazer", "Salesforce Trailblazer Community", "trailhead.salesforce.com", 88, 0.1),
    ("spiceworks", "Spiceworks Community", "community.spiceworks.com", 82, 0.1),
    ("moz-community", "Moz Q&A", "moz.com", 90, 0.15),
    ("superuser", "Super User", "superuser.com", 92, 0.4),
    ("serverfault", "Server Fault", "serverfault.com", 90, 0.35),
    ("mathoverflow", "MathOverflow", "mathoverflow.net", 86, 0.2),
]
for slug, name, domain, auth, weight in _FORUMS:
    add(slug, name, domain, "forum", auth, submit_url=f"https://{domain}", link_type="nofollow", effort=4,
        required_fields=("display_name", "website"), tags=("forum", "participation"),
        ai_training_signal=True, llm_citation_weight=weight,
        notes="Answer questions you are genuinely qualified to answer. These threads are scraped into training data, "
              "so a good answer keeps paying for years.")

# ---------------------------------------------------------------------------
# 25. Journalist / expert-source platforms
# ---------------------------------------------------------------------------
_SOURCE = [
    ("featured", "Featured (formerly Terkel)", "featured.com", 74, True),
    ("qwoted", "Qwoted", "qwoted.com", 72, True),
    ("sourcebottle", "SourceBottle", "sourcebottle.com", 66, True),
    ("responsesource", "ResponseSource", "responsesource.com", 70, False),
    ("expertfile", "ExpertFile", "expertfile.com", 68, True),
    ("muck-rack", "Muck Rack", "muckrack.com", 84, False),
]
for slug, name, domain, auth, free in _SOURCE:
    add(slug, name, domain, "guest_post", auth, submit_url=f"https://{domain}", link_type="dofollow",
        is_free=free, effort=3,
        required_fields=("display_name", "website", "short_description", "email"),
        tags=("pr", "expert-quote", "editorial"), llm_citation_weight=0.1,
        notes="Answer reporter queries with a substantive, quotable opinion. Slow, but produces genuine editorial links "
              "on news domains you cannot otherwise reach.")


def main() -> None:
    slugs = [r["slug"] for r in ROWS]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise SystemExit(f"duplicate slugs: {sorted(dupes)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ROWS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    by_cat: dict[str, int] = {}
    for r in ROWS:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    print(f"wrote {len(ROWS)} link sources -> {OUT.relative_to(ROOT)}")
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:<20} {n}")


if __name__ == "__main__":
    main()

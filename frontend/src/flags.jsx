const COUNTRY_ISO = {
  argentina: "ar",
  australia: "au",
  austria: "at",
  azerbaijan: "az",
  bahrain: "bh",
  belgium: "be",
  brazil: "br",
  canada: "ca",
  china: "cn",
  france: "fr",
  germany: "de",
  "great britain": "gb",
  hungary: "hu",
  india: "in",
  italy: "it",
  japan: "jp",
  korea: "kr",
  malaysia: "my",
  mexico: "mx",
  monaco: "mc",
  morocco: "ma",
  netherlands: "nl",
  portugal: "pt",
  qatar: "qa",
  russia: "ru",
  "saudi arabia": "sa",
  singapore: "sg",
  "south africa": "za",
  "south korea": "kr",
  spain: "es",
  sweden: "se",
  switzerland: "ch",
  turkey: "tr",
  uae: "ae",
  uk: "gb",
  "united arab emirates": "ae",
  "united kingdom": "gb",
  "united states": "us",
  usa: "us",
};

export function countryIso(country) {
  if (!country) return "";
  return COUNTRY_ISO[String(country).trim().toLowerCase()] || "";
}

export function CountryFlag({ country }) {
  const iso = countryIso(country);
  if (!iso) {
    return <span className="flag flag-fallback" aria-hidden="true" />;
  }
  return (
    <img
      className="flag-img"
      src={`https://flagcdn.com/w40/${iso}.png`}
      srcSet={`https://flagcdn.com/w80/${iso}.png 2x`}
      alt=""
      width="22"
      height="15"
    />
  );
}

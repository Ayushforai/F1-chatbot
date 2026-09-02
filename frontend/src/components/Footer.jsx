function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="4" fill="#0A66C2" />
      <path
        fill="#fff"
        d="M7.1 9.2H4.7V19h2.4V9.2zM5.9 5C5.1 5 4.5 5.6 4.5 6.4c0 .8.6 1.4 1.4 1.4s1.4-.6 1.4-1.4C7.3 5.6 6.7 5 5.9 5zM19.5 13.4c0-2.8-1.5-4.2-3.6-4.2-1.7 0-2.4.9-2.8 1.6V9.2h-2.4c0 1.1 0 9.8 0 9.8h2.4v-5.5c0-.3 0-.6.1-.8.3-.6.9-1.2 1.9-1.2 1.3 0 1.9.9 1.9 2.3V19h2.5v-5.6z"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#fff"
        d="M12 2C6.5 2 2 6.6 2 12.2c0 4.5 2.9 8.3 6.9 9.6.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.4-3.4-1.4-.4-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.6 2.4 1.1 3 .9.1-.7.4-1.1.6-1.4-2.2-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1 .8-.2 1.6-.3 2.5-.3s1.7.1 2.5.3c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.7.7 1.1 1.6 1.1 2.7 0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5 4-1.3 6.9-5.1 6.9-9.6C22 6.6 17.5 2 12 2z"
      />
    </svg>
  );
}

function GmailIcon() {
  return (
    <svg viewBox="52 42 88 66" aria-hidden="true">
      <path fill="#4285F4" d="M58 108h14V74L52 59v43c0 3.32 2.69 6 6 6" />
      <path fill="#34A853" d="M120 108h14c3.32 0 6-2.69 6-6V59l-20 15" />
      <path fill="#FBBC04" d="M120 48v26l20-15v-8c0-7.42-8.47-11.65-14.4-7.2" />
      <path fill="#EA4335" d="M72 74V48l24 18 24-18v26L96 92" />
      <path fill="#C5221F" d="M52 51v8l20 15V48l-5.6-4.2c-5.94-4.45-14.4-.22-14.4 7.2" />
    </svg>
  );
}

const LINKS = [
  {
    label: "LinkedIn",
    href: "https://www.linkedin.com/in/ayush-chaudhary-ba00b8248/",
    Icon: LinkedInIcon,
  },
  {
    label: "GitHub",
    href: "https://github.com/Ayushforai",
    Icon: GitHubIcon,
  },
  {
    label: "Gmail",
    href: "mailto:ayushc90210@gmail.com",
    Icon: GmailIcon,
  },
];

export default function Footer() {
  return (
    <footer className="site-footer">
      <p className="footer-name">AYUSH CHAUDHARY</p>
      <div className="footer-links">
        {LINKS.map(({ label, href, Icon }) => (
          <a
            key={label}
            href={href}
            target={href.startsWith("mailto:") ? undefined : "_blank"}
            rel={href.startsWith("mailto:") ? undefined : "noopener noreferrer"}
            aria-label={label}
            title={label}
          >
            <Icon />
          </a>
        ))}
      </div>
    </footer>
  );
}

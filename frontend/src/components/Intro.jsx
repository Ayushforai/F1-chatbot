import { useEffect } from "react";
import rcLogo from "../assets/rc-logo.png";

export default function Intro({ onDone }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, 3500);
    return () => window.clearTimeout(timer);
  }, [onDone]);

  return (
    <div className="intro" role="presentation">
      <div className="intro-rays" aria-hidden="true">
        <span className="intro-line intro-line--left intro-line--top" />
        <span className="intro-line intro-line--left intro-line--bot" />
        <span className="intro-line intro-line--right intro-line--top" />
        <span className="intro-line intro-line--right intro-line--bot" />
      </div>
      <div className="intro-stage">
        <img className="intro-burst" src={rcLogo} alt="" aria-hidden="true" />
        <img className="intro-logo" src={rcLogo} alt="Racecoe" />
      </div>
    </div>
  );
}

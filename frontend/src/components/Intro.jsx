import { useEffect, useRef, useState } from "react";
import rcLogo from "../assets/rc-logo.png";

const REDUCE_MS = 1400;
const FULL_MS = 2600;
const LOAD_CAP_MS = 1500;
const EXIT_MS = 700;

export default function Intro({ onDone }) {
  const imgRef = useRef(null);
  const [live, setLive] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let liveMarked = false;
    const timers = [];
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const visibleMs = reduce ? REDUCE_MS : FULL_MS;

    const markLive = () => {
      if (cancelled || liveMarked) return;
      liveMarked = true;
      setLive(true);
      timers.push(
        window.setTimeout(() => {
          if (cancelled) return;
          setExiting(true);
          timers.push(
            window.setTimeout(() => {
              if (!cancelled) onDone();
            }, reduce ? 0 : EXIT_MS),
          );
        }, visibleMs),
      );
    };

    const img = imgRef.current;
    if (img?.complete && img.naturalWidth > 0) {
      markLive();
    } else {
      img?.addEventListener("load", markLive);
      img?.addEventListener("error", markLive);
      timers.push(window.setTimeout(markLive, LOAD_CAP_MS));
    }

    return () => {
      cancelled = true;
      img?.removeEventListener("load", markLive);
      img?.removeEventListener("error", markLive);
      timers.forEach((id) => window.clearTimeout(id));
    };
  }, [onDone]);

  return (
    <div
      className={`intro${live ? " is-live" : ""}${exiting ? " is-exiting" : ""}`}
      role="presentation"
    >
      <div className="intro-rays" aria-hidden="true">
        <span className="intro-line intro-line--left intro-line--top" />
        <span className="intro-line intro-line--left intro-line--bot" />
        <span className="intro-line intro-line--right intro-line--top" />
        <span className="intro-line intro-line--right intro-line--bot" />
      </div>
      <div className="intro-stage">
        <img className="intro-burst" src={rcLogo} alt="" aria-hidden="true" />
        <img
          ref={imgRef}
          className="intro-logo"
          src={rcLogo}
          alt="Racecoe"
          decoding="async"
          fetchPriority="high"
        />
      </div>
    </div>
  );
}

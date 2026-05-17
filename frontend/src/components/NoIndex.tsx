import { useEffect } from "react";

interface NoIndexProps {
  nofollow?: boolean;
}

function setAttr(selector: string, attr: string, value: string) {
  document.querySelector(selector)?.setAttribute(attr, value);
}

export default function NoIndex({ nofollow = false }: NoIndexProps) {
  useEffect(() => {
    const followPart = nofollow ? "nofollow" : "follow";
    setAttr('meta[name="robots"]', "content", `noindex, ${followPart}`);
  }, [nofollow]);
  return null;
}

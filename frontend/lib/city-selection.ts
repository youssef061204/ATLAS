"use client";

import { useSyncExternalStore } from "react";

export const CITY_CHOICES = [
  { id: "toronto", name: "Toronto", region: "Ontario, Canada" },
  { id: "london", name: "London", region: "United Kingdom" },
  { id: "seattle", name: "Seattle", region: "Washington, United States" },
  { id: "austin", name: "Austin", region: "Texas, United States" },
  { id: "calgary", name: "Calgary", region: "Alberta, Canada" },
] as const;
const storageKey = "atlas:city:v1";
const eventName = "atlas:city-change";

export function readSelectedCity() {
  if (typeof window === "undefined") return "toronto";
  const parameter = new URL(window.location.href).searchParams.get("city");
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(storageKey);
  } catch {
    /* Storage can be disabled; URL selection still works. */
  }
  return (
    CITY_CHOICES.find((city) => city.id === (parameter ?? stored))?.id ??
    "toronto"
  );
}

export function selectCity(city: string) {
  if (!CITY_CHOICES.some((choice) => choice.id === city)) return;
  try {
    window.localStorage.setItem(storageKey, city);
  } catch {
    /* URL is the fallback. */
  }
  const url = new URL(window.location.href);
  url.searchParams.set("city", city);
  url.searchParams.delete("camera");
  url.searchParams.delete("experiment");
  window.history.replaceState(null, "", url);
  window.dispatchEvent(new Event(eventName));
}

function subscribe(callback: () => void) {
  window.addEventListener(eventName, callback);
  window.addEventListener("popstate", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(eventName, callback);
    window.removeEventListener("popstate", callback);
    window.removeEventListener("storage", callback);
  };
}

export function useCitySelection() {
  return [
    useSyncExternalStore(subscribe, readSelectedCity, () => "toronto"),
    selectCity,
  ] as const;
}

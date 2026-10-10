import { NetworkStudio } from "@/components/network-studio";
import { ControlStudyV5 } from "@/components/control-study-v5";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ cohort?: string }>;
}) {
  const { cohort } = await searchParams;
  if (cohort === "atlas-5") return <ControlStudyV5 />;
  return <NetworkStudio />;
}

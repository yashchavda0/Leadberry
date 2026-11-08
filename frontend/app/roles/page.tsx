"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Guard } from "@/components/Session";
import { Loading } from "@/components/Ui";

export default function RolesPage() {
  return <Guard permission="roles.view"><LegacyRoles /></Guard>;
}

function LegacyRoles() {
  const router = useRouter();
  useEffect(() => { router.replace("/users?tab=roles"); }, [router]);
  return <Loading />;
}

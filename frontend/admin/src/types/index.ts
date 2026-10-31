export interface Issue { question: string; reason: string }

export type Role = "platform_admin" | "school_manager" | "teacher" | "parent";

export interface User {
  id: string;
  name: string;
  email: string;
  phone: string;
  role: Role;
  admin_role: "super_admin" | "admin" | "viewer" | null;
  school: { id: string; name: string; status: "PENDING" | "ACTIVE" | "SUSPENDED" } | null;
  status: string;
  must_change_password: boolean;
  has_password: boolean;
  google_linked: boolean;
  last_login_at: string | null;
}

export interface Session { access_token: string; user: User }

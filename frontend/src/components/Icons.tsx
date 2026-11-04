import type { SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & {

  size?: number;

};

const defaultProps = (size = 18): SVGProps<SVGSVGElement> => ({

  width: size,

  height: size,

  viewBox: "0 0 24 24",

  fill: "none",

  stroke: "currentColor",

  strokeWidth: 2,

  strokeLinecap: "round",

  strokeLinejoin: "round",

  "aria-hidden": "true",

});

export const IconDashboard = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <rect width="7" height="9" x="3" y="3" rx="1" />

    <rect width="7" height="5" x="14" y="3" rx="1" />

    <rect width="7" height="9" x="14" y="12" rx="1" />

    <rect width="7" height="5" x="3" y="16" rx="1" />

  </svg>

);

export const IconExam = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />

    <path d="M6 6h10" />

    <path d="M6 10h10" />

    <path d="M6 14h6" />

  </svg>

);

export const IconEvaluation = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m9 11 3 3L22 4" />

    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />

  </svg>

);

export const IconResults = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />

    <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />

    <path d="M4 22h16" />

    <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />

    <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />

    <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />

  </svg>

);

export const IconClasses = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />

    <circle cx="9" cy="7" r="4" />

    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />

    <path d="M16 3.13a4 4 0 0 1 0 7.75" />

  </svg>

);

export const IconStudents = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M21.42 10.922a1 1 0 0 0-.019-.838L12.83 2.18a2 2 0 0 0-1.66 0L2.6 10.084a1 1 0 0 0 0 1.832l8.57 7.904a2 2 0 0 0 1.66 0l8.57-7.904a1 1 0 0 0 .02-.994Z" />

    <path d="M6 13.5v5c0 1.5 2.686 3 6 3s6-1.5 6-3v-5" />

  </svg>

);

export const IconSubjects = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />

    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />

  </svg>

);

export const IconSettings = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />

    <circle cx="12" cy="12" r="3" />

  </svg>

);

export const IconFileText = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />

    <path d="M14 2v4a2 2 0 0 0 2 2h4" />

    <path d="M10 9H8" />

    <path d="M16 13H8" />

    <path d="M16 17H8" />

  </svg>

);

export const IconSearch = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <circle cx="11" cy="11" r="8" />

    <path d="m21 21-4.3-4.3" />

  </svg>

);

export const IconPlus = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M5 12h14" />

    <path d="M12 5v14" />

  </svg>

);

export const IconCheck = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M20 6 9 17l-5-5" />

  </svg>

);

export const IconCheckCircle = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />

    <path d="m9 11 3 3L22 4" />

  </svg>

);

export const IconX = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M18 6 6 18" />

    <path d="m6 6 12 12" />

  </svg>

);

export const IconAlertCircle = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <circle cx="12" cy="12" r="10" />

    <line x1="12" x2="12" y1="8" y2="12" />

    <line x1="12" x2="12.01" y1="16" y2="16" />

  </svg>

);

export const IconAlertTriangle = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />

    <line x1="12" x2="12" y1="9" y2="13" />

    <line x1="12" x2="12.01" y1="17" y2="17" />

  </svg>

);

export const IconCopy = ({ size = 18, ...p }: IconProps) => (
  <svg {...defaultProps(size)} {...p}>
    <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
    <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
  </svg>
);

export const IconInfo = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <circle cx="12" cy="12" r="10" />

    <path d="M12 16v-4" />

    <path d="M12 8h.01" />

  </svg>

);

export const IconClock = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <circle cx="12" cy="12" r="10" />

    <polyline points="12 6 12 12 16 14" />

  </svg>

);

export const IconDownload = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />

    <polyline points="7 10 12 15 17 10" />

    <line x1="12" x2="12" y1="15" y2="3" />

  </svg>

);

export const IconUpload = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />

    <polyline points="17 8 12 3 7 8" />

    <line x1="12" x2="12" y1="3" y2="15" />

  </svg>

);

export const IconTrash = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M3 6h18" />

    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />

    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />

  </svg>

);

export const IconEdit = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />

    <path d="m15 5 4 4" />

  </svg>

);

export const IconEye = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />

    <circle cx="12" cy="12" r="3" />

  </svg>

);

export const IconZoomIn = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <circle cx="11" cy="11" r="8" />

    <line x1="21" x2="16.65" y1="21" y2="16.65" />

    <line x1="11" x2="11" y1="8" y2="14" />

    <line x1="8" x2="14" y1="11" y2="11" />

  </svg>

);

export const IconZoomOut = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <circle cx="11" cy="11" r="8" />

    <line x1="21" x2="16.65" y1="21" y2="16.65" />

    <line x1="8" x2="14" y1="11" y2="11" />

  </svg>

);

export const IconRotateCcw = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />

    <path d="M3 3v5h5" />

  </svg>

);

export const IconChevronLeft = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m15 18-6-6 6-6" />

  </svg>

);

export const IconChevronRight = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m9 18 6-6-6-6" />

  </svg>

);

export const IconChevronDown = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m6 9 6 6 6-6" />

  </svg>

);

export const IconSparkles = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />

    <path d="M5 3v4" />

    <path d="M19 17v4" />

    <path d="M3 5h4" />

    <path d="M17 19h4" />

  </svg>

);

export const IconLogOut = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />

    <polyline points="16 17 21 12 16 7" />

    <line x1="21" x2="9" y1="12" y2="12" />

  </svg>

);

export const IconMenu = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <line x1="4" x2="20" y1="12" y2="12" />

    <line x1="4" x2="20" y1="6" y2="6" />

    <line x1="4" x2="20" y1="18" y2="18" />

  </svg>

);

export const IconMail = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <rect width="20" height="16" x="2" y="4" rx="2" />

    <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />

  </svg>

);

export const IconLock = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />

    <path d="M7 11V7a5 5 0 0 1 10 0v4" />

  </svg>

);

export const IconEyeOff = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />

    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />

    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />

    <line x1="2" x2="22" y1="2" y2="22" />

  </svg>

);

export const IconShield = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />

  </svg>

);

export const IconArrowRight = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M5 12h14" />

    <path d="m12 5 7 7-7 7" />

  </svg>

);

export const IconLogIn = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />

    <polyline points="10 17 15 12 10 7" />

    <line x1="15" x2="3" y1="12" y2="12" />

  </svg>

);

export const IconBell = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />

    <path d="M13.73 21a2 2 0 0 1-3.46 0" />

  </svg>

);

export const IconHome = ({ size = 18, ...p }: IconProps) => (

  <svg {...defaultProps(size)} {...p}>

    <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />

    <polyline points="9 22 9 12 15 12 15 22" />

  </svg>

);


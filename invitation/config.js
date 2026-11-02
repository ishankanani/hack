/* Edit this file to personalise the invitation. Everything on the page is rendered from it.
   Photos: set `photo` to an image URL/path (e.g. "photos/groom.jpg"); leave "" to show the illustrated monogram. */
window.INVITE = {
  groom: { first: "Rahul", full: "Rahul Verma", parents: "Son of Suresh Verma & Anita Verma", family: "Verma", photo: "" },
  bride: { first: "Priya", full: "Priya Sharma", parents: "Daughter of Rakesh Sharma & Sunita Sharma", family: "Sharma", photo: "" },

  // Main muhurtham (used for countdown, save-the-date and footer). Include the timezone offset.
  weddingAt: "2026-12-17T19:00:00+05:30",
  mainVenue: "Shubh Vivah Banquet Hall",
  hashtag: "#RahulWedsPriya",

  family: {
    groom: [{ role: "Brother", name: "Rohan Verma", photo: "" }],
    bride: [{ role: "Sister", name: "Nisha Sharma", photo: "" }],
  },

  events: [
    { icon: "🌼", name: "Haldi", note: "Family only", date: "14 Dec 2026 · 10:00 AM", venue: "Sharma Residence", dress: "Yellow" },
    { icon: "🎨", name: "Mehndi", date: "15 Dec 2026 · 4:00 PM", venue: "The Grand Lawns", dress: "Green & Gold" },
    { icon: "🎶", name: "Sangeet", date: "16 Dec 2026 · 7:00 PM", venue: "The Grand Lawns", dress: "Festive Indo-Western" },
    { icon: "💍", name: "Wedding", date: "17 Dec 2026 · 7:00 PM", venue: "Shubh Vivah Banquet Hall", dress: "Traditional Formal" },
    { icon: "🥂", name: "Reception", date: "18 Dec 2026 · 8:00 PM", venue: "Shubh Vivah Banquet Hall", dress: "Formal" },
  ],

  story: [
    { when: "March 2019", title: "We First Met", text: "A mutual friend's birthday party in Delhi — Rahul spilled chai on Priya's dupatta." },
    { when: "June 2021", title: "First Trip Together", text: "A weekend in Manali that turned into a week — neither of us wanted to come back." },
    { when: "December 2025", title: "The Proposal", text: "On a rooftop in Udaipur, under fairy lights, with both families secretly watching." },
  ],

  gallery: [
    { photo: "", caption: "Together Forever", sub: "A beautiful beginning" },
    { photo: "", caption: "The Roka", sub: "Two families, one heart" },
    { photo: "", caption: "Manali Days", sub: "Mountains & chai" },
    { photo: "", caption: "Under Fairy Lights", sub: "The day she said yes" },
    { photo: "", caption: "Forever Begins", sub: "Mangala muhurtham" },
  ],

  venues: [
    { events: "Wedding, Reception", name: "Shubh Vivah Banquet Hall", address: "MG Road, Gurugram",
      schedule: "Thursday, 17 December 2026 · 7:00 PM | Friday, 18 December 2026 · 8:00 PM" },
    { events: "Haldi", name: "Sharma Residence", address: "B-12, Green Park, New Delhi",
      schedule: "Monday, 14 December 2026 · 10:00 AM", scheduleLabel: "Date & Time" },
    { events: "Mehndi, Sangeet", name: "The Grand Lawns", address: "Sector 44, Gurugram",
      schedule: "Tuesday, 15 December 2026 · 4:00 PM | Wednesday, 16 December 2026 · 7:00 PM" },
  ],

  contacts: [
    { side: "The Groom's Family", name: "Rohan Verma", role: "Groom's Brother", phone: "+91 98765 43210" },
    { side: "The Bride's Family", name: "Nisha Sharma", role: "Bride's Sister", phone: "+91 91234 56789" },
  ],

  // RSVPs are sent as a pre-filled WhatsApp message to this number (country code, digits only).
  rsvpWhatsApp: "919876543210",

  wishes: [
    { text: "So happy for you both! Wishing you a lifetime of love and laughter.", by: "Anjali Mehta, Priya's college friend" },
    { text: "Finally! Can't wait to dance at your sangeet, bhai.", by: "Vikram Singh, Rahul's cousin" },
    { text: "May your journey together be as beautiful as your love story.", by: "The Kapoor Family, Family friends" },
  ],
};

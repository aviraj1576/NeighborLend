import React from 'react';
import LegalPage, { CONTACT_EMAIL, Note } from '../components/legal/LegalPage';

const contactLine = CONTACT_EMAIL
  ? <>email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></>
  : <>use the chat option in the app</>;

const SECTIONS = [
  {
    id: 'who',
    title: 'Who we are and what this covers',
    body: (
      <>
        <p>
          NeighborLend is a website where neighbors lend items to each other and borrow them. We run it from
          Delhi, India. This policy explains what personal information we collect when you use NeighborLend,
          why we collect it, who can see it, and what you can ask us to do with it.
        </p>
        <p>
          It covers the NeighborLend website and everything you do on it: browsing, listing an item,
          messaging, borrowing, returning, disputes and support chats. It does not cover other websites that
          you reach through a link.
        </p>
      </>
    ),
  },
  {
    id: 'collect',
    title: 'What we collect',
    body: (
      <>
        <p>We collect the following, mostly because you give it to us.</p>
        <ul>
          <li><strong>Account details.</strong> Your name, username, email address and, if you add one, your phone number. Your password is stored only as a one-way hash, so we cannot read it. If you sign in with Google we receive your name, email address and profile picture from Google.</li>
          <li><strong>Listings and requests.</strong> The item description, category, price, photos, the pickup area you type in, the map coordinates behind it and how far you are willing to lend.</li>
          <li><strong>Conversations.</strong> Messages, rental offers, counter-offers, ratings and the comments you write about other users.</li>
          <li><strong>Handover and return.</strong> The six condition photos taken when an item is handed over and again when it comes back, the result of comparing them, and any dispute you raise or are part of.</li>
          <li><strong>Support.</strong> Your chats with our support assistant and with our team, and the page or step you opened the chat from.</li>
          <li><strong>Device and use.</strong> Your approximate location if you allow your browser to share it, so we can show nearby items. Our servers also log technical details such as your IP address, the time and the page requested, to keep the service secure.</li>
          <li><strong>Notifications.</strong> The in-app notices we create for you, for example that a rental offer arrived.</li>
        </ul>
      </>
    ),
  },
  {
    id: 'use',
    title: 'How we use it',
    body: (
      <>
        <ul>
          <li>To create your account, check your email address and keep you signed in.</li>
          <li>To show listings near you, and to let you and another user agree a rental and carry it out.</li>
          <li>To check listing photos automatically and flag items that may not belong on NeighborLend.</li>
          <li>To work out each user&rsquo;s trust score from ratings and completed rentals.</li>
          <li>To settle disputes about the condition of an item.</li>
          <li>To answer support requests and keep the service secure and free of fraud.</li>
          <li>To meet our legal duties.</li>
        </ul>
        <p>We do not sell your personal information and we do not show advertising.</p>
      </>
    ),
  },
  {
    id: 'photos',
    title: 'Condition photos and automated checks',
    body: (
      <>
        <p>
          Two kinds of automated processing touch your photos, and neither one makes a final decision about you.
        </p>
        <ul>
          <li><strong>Listing photos.</strong> A recognition model that runs on our own servers suggests what the item is, for example a drill or a bicycle. Nothing is sent to another company for this.</li>
          <li><strong>Condition photos.</strong> When a rental ends, the before and after photos are compared by an AI vision service. We use Google&rsquo;s Gemini service for this, so these photos are sent to Google for that comparison. The result is a warning that points to places worth a look. It is not a verdict.</li>
        </ul>
        <p>
          Condition photos are private. Only the lender and the borrower of that rental can open them, and only
          while signed in. If a dispute is raised, or you ask support for help with a rental, NeighborLend
          administrators can see them too. The link the lender shares works only for those two people and stops
          working after it expires or the rental closes.
        </p>
        <Note>A person always decides a dispute. The AI comparison is only one of the things they look at.</Note>
      </>
    ),
  },
  {
    id: 'sharing',
    title: 'Who we share it with',
    body: (
      <>
        <p><strong>Other users.</strong> Your name, username, trust score, ratings, listings and the messages in a conversation are visible to the people they are meant for. The photos and records of a rental are visible to the two people in it.</p>
        <p><strong>Companies that help us run NeighborLend.</strong> They handle data only to provide their service to us.</p>
        <ul>
          <li>Supabase: our database and photo storage.</li>
          <li>Render: the servers that run NeighborLend.</li>
          <li>Vercel: the hosting of the website you are reading.</li>
          <li>Brevo: sending verification emails.</li>
          <li>Google: Sign in with Google, the fonts we load, and the condition photo comparison described above.</li>
        </ul>
        <p><strong>Others.</strong> We share information when the law requires it, to protect someone&rsquo;s safety, or if NeighborLend is sold or merged. In that case we will tell you and the same protections will continue to apply.</p>
      </>
    ),
  },
  {
    id: 'storage',
    title: 'Cookies and browser storage',
    body: (
      <>
        <p>
          When you sign in, your browser keeps a sign-in token in its local storage so you stay signed in. It is
          removed when you log out. We do not use advertising cookies or third-party analytics.
        </p>
        <p>
          Google Sign-In and Google Fonts load from Google. Google may set its own cookies when they do, under
          Google&rsquo;s own privacy policy.
        </p>
      </>
    ),
  },
  {
    id: 'keep',
    title: 'How long we keep it',
    body: (
      <>
        <p>
          We keep your information while your account is open. Email verification codes expire after ten minutes.
          If you close your account we delete or anonymize your personal details, except what we still need to
          settle a dispute, keep the service safe or meet a legal duty. Condition photos and dispute records are
          kept for as long as a dispute or a follow-up on it may need them.
        </p>
      </>
    ),
  },
  {
    id: 'security',
    title: 'How we protect it',
    body: (
      <>
        <ul>
          <li>Passwords are stored as hashes, never in plain text.</li>
          <li>Traffic between your browser and NeighborLend is encrypted with HTTPS.</li>
          <li>Every request to see a rental, a photo or a conversation is checked on our servers against who you are.</li>
          <li>Administrator access is limited to named accounts, and each decision an administrator makes is logged.</li>
        </ul>
        <p>No service is perfectly secure. If you think your account has been used by someone else, change your password and tell us straight away.</p>
      </>
    ),
  },
  {
    id: 'rights',
    title: 'Your choices',
    body: (
      <>
        <p>You can ask us to:</p>
        <ul>
          <li>show you the personal information we hold about you;</li>
          <li>correct it (you can edit your profile yourself in the app);</li>
          <li>delete your account and personal information, subject to the limits in &ldquo;How long we keep it&rdquo;;</li>
          <li>stop using your location, which you can also do in your browser settings.</li>
        </ul>
        <p>
          To make a request or a complaint, {contactLine}. We aim to reply within 30 days. We handle personal
          information in line with the data protection laws that apply in India.
        </p>
      </>
    ),
  },
  {
    id: 'children',
    title: 'Children',
    body: (
      <p>
        NeighborLend is for people aged 18 and over. We do not knowingly collect information from anyone
        younger. If you think a child has given us their details, tell us and we will remove them.
      </p>
    ),
  },
  {
    id: 'abroad',
    title: 'Where data is processed',
    body: (
      <p>
        Some of the companies listed above run servers outside India, so your information may be processed
        there. We choose providers that protect it to a standard comparable to this policy.
      </p>
    ),
  },
  {
    id: 'changes',
    title: 'Changes to this policy',
    body: (
      <p>
        If we change this policy we will update the date at the top. For changes that matter to you, such as a new
        way of using your photos, we will also tell you in the app before they apply.
      </p>
    ),
  },
];

export default function PrivacyPolicy() {
  return (
    <LegalPage
      title="Privacy Policy"
      lead="What information NeighborLend collects, why we collect it, and who can see it."
      updated="14 November 2026"
      sections={SECTIONS}
      other={{ to: '/terms', label: 'Read the Terms of Service' }}
    />
  );
}

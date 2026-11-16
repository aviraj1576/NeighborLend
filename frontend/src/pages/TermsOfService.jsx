import React from 'react';
import { Link } from 'react-router-dom';
import LegalPage, { CONTACT_EMAIL, Note } from '../components/legal/LegalPage';

const contactLine = CONTACT_EMAIL
  ? <>email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></>
  : <>use the chat option in the app</>;

const SECTIONS = [
  {
    id: 'agreement',
    title: 'Agreeing to these terms',
    body: (
      <>
        <p>
          These terms are the agreement between you and NeighborLend, which is run from Delhi, India. By creating
          an account or using the website you accept them. If you do not accept them, please do not use
          NeighborLend.
        </p>
        <p>Our <Link to="/privacy">Privacy Policy</Link> explains how we handle your information and is part of this agreement.</p>
      </>
    ),
  },
  {
    id: 'accounts',
    title: 'Your account',
    body: (
      <ul>
        <li>You must be 18 or older.</li>
        <li>Give accurate details and keep them up to date. You may have one account.</li>
        <li>Keep your password to yourself. You are responsible for what happens under your account.</li>
        <li>Tell us if you think someone else has got into your account.</li>
      </ul>
    ),
  },
  {
    id: 'what',
    title: 'What NeighborLend is, and is not',
    body: (
      <>
        <p>
          NeighborLend helps neighbors find each other. When one person lends an item to another, the rental is
          between those two people. NeighborLend is not a party to it. We do not own the items, inspect them,
          insure them or guarantee that a person will behave well.
        </p>
        <p>
          NeighborLend does not handle money. You and the other person agree a price in the app and settle it
          between yourselves. Trust scores and ratings are a guide made from what other users reported. They are
          not a promise.
        </p>
      </>
    ),
  },
  {
    id: 'listings',
    title: 'Listings and requests',
    body: (
      <>
        <p>When you list an item or post a request you promise that:</p>
        <ul>
          <li>you own the item or have the right to lend it, and the photos and description are accurate;</li>
          <li>the item is legal to lend and safe to use as described;</li>
          <li>you are not listing weapons, illegal goods, stolen goods, hazardous materials or anything that needs a licence you do not hold.</li>
        </ul>
        <p>We may flag, pause or remove a listing that breaks these rules, including after an automatic check of its photos.</p>
      </>
    ),
  },
  {
    id: 'rentals',
    title: 'Lending and borrowing',
    body: (
      <>
        <p>A rental follows these steps in the app.</p>
        <ul>
          <li><strong>Agree.</strong> You agree the price and dates through an offer that the other person accepts.</li>
          <li><strong>Hand over.</strong> The lender takes six condition photos (front, back, left, right, top and bottom) and shares a private link with the borrower. The borrower looks at the photos and confirms they received the item. That starts the rental period.</li>
          <li><strong>Return.</strong> The borrower takes the same six photos and submits them. This can be done early, on any day before the due date.</li>
          <li><strong>Review.</strong> The lender approves the return or raises a dispute. If the lender does neither within 72 hours of the return photos being submitted, the return is approved automatically.</li>
        </ul>
        <p>
          While you have an item, you look after it and return it in the condition you received it, apart from
          ordinary wear. Return it on time, and tell the lender early if you will be late.
        </p>
      </>
    ),
  },
  {
    id: 'ai',
    title: 'Condition checks and the AI comparison',
    body: (
      <>
        <p>
          The before and after photos are compared automatically and the result points to places that look
          different. It can miss real damage, and it can flag things that are only a change in light or angle. It
          cannot see inside an item, so it cannot tell you whether a device still works.
        </p>
        <Note>Treat the comparison as a prompt to look closely. You stay responsible for checking the item yourself.</Note>
      </>
    ),
  },
  {
    id: 'disputes',
    title: 'Disputes',
    body: (
      <>
        <p>
          A lender can raise a dispute once the return photos are submitted. If an item was never returned, the
          lender can raise one seven days after the due date. Each rental can have one open dispute.
        </p>
        <p>
          A NeighborLend administrator then looks at both sets of photos, the comparison and the messages, and
          decides: in favor of the lender, in favor of the borrower, or partly for each with a written note. Both
          people are told, and the rental is closed.
        </p>
        <p>
          That decision settles the matter on NeighborLend. Because we do not handle money, we do not collect or
          pay anything ourselves. The decision does not take away any legal right you have to seek a remedy
          elsewhere.
        </p>
      </>
    ),
  },
  {
    id: 'content',
    title: 'Your content',
    body: (
      <p>
        You keep ownership of what you post: your listings, photos and messages. You give NeighborLend a licence
        to store, show and process it only as needed to run the service. That includes sending condition photos to
        the comparison service described in the Privacy Policy. The licence ends when you delete the content or
        your account, apart from what we must keep for a dispute or by law.
      </p>
    ),
  },
  {
    id: 'conduct',
    title: 'How to behave',
    body: (
      <>
        <p>Do not:</p>
        <ul>
          <li>harass, threaten or discriminate against anyone;</li>
          <li>deceive other users, post fake reviews or use more than one account to do it;</li>
          <li>upload photos that are not of the item, or that have been edited to hide damage;</li>
          <li>share other people&rsquo;s personal details or private photos;</li>
          <li>try to get past our security, scrape the site or use someone else&rsquo;s account.</li>
        </ul>
      </>
    ),
  },
  {
    id: 'support',
    title: 'Support and messages from us',
    body: (
      <p>
        We send in-app notifications about your rentals and emails for things like verifying your address. The
        &ldquo;Chat with us&rdquo; button opens a chat with an automated assistant that answers common questions.
        It follows fixed rules and does not use artificial intelligence. You can ask it to pass your chat to a
        person on our team.
      </p>
    ),
  },
  {
    id: 'ending',
    title: 'Suspending or closing an account',
    body: (
      <p>
        We may suspend or close an account that breaks these terms or puts others at risk, and we will say why
        when we can. You may stop using NeighborLend at any time and ask us to close your account. Sections that
        are meant to continue, such as disputes and liability, continue after that.
      </p>
    ),
  },
  {
    id: 'liability',
    title: 'Limits on our responsibility',
    body: (
      <>
        <p>
          NeighborLend is provided as it is. We work to keep it running and accurate, but we cannot promise it
          will always be available or free of errors.
        </p>
        <p>
          To the extent the law allows, NeighborLend is not responsible for loss, damage or injury that comes from
          a rental, from an item, or from what a user does or says. Nothing in these terms removes a responsibility
          that the law does not allow us to remove.
        </p>
      </>
    ),
  },
  {
    id: 'changes',
    title: 'Changes to the service or these terms',
    body: (
      <p>
        We may change NeighborLend or these terms. We will update the date at the top and, for changes that
        matter, tell you in the app before they apply. If you keep using NeighborLend after a change, you accept
        it.
      </p>
    ),
  },
  {
    id: 'law',
    title: 'Governing law',
    body: (
      <p>
        These terms are governed by the laws of India, and the courts in Delhi can hear any dispute about them.
        To raise a concern with us first, {contactLine}.
      </p>
    ),
  },
];

export default function TermsOfService() {
  return (
    <LegalPage
      title="Terms of Service"
      lead="The rules for using NeighborLend as a lender, a borrower or both."
      updated="14 November 2026"
      sections={SECTIONS}
      other={{ to: '/privacy', label: 'Read the Privacy Policy' }}
    />
  );
}

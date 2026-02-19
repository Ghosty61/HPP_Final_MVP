document.addEventListener("DOMContentLoaded", () => {
    // Initialize EmailJS with public key from config
    if (typeof emailjs !== "undefined" && EMAIL_CONFIG.publicKey !== "YOUR_EMAILJS_PUBLIC_KEY") {
        emailjs.init(EMAIL_CONFIG.publicKey);
    }

    const roiForm = document.getElementById("roiForm");

    roiForm.addEventListener("submit", (e) => {
        e.preventDefault();

        // 1. Capture Inputs
        const investment = 850000; // Real-world SME Machine Cost
        const annualVolume = parseFloat(document.getElementById('annualVolume').value);
        const currentWaste = 0.20; // 20% manual shucking waste
        const pricePerKg = parseFloat(document.getElementById('pricePerKg').value);

        // 2. Logic: HPP at 87,000 psi recovers 100% of meat (22% yield gain)
        const recoveredWasteValue = (annualVolume * currentWaste) * pricePerKg;
        const annualOpCosts = 25000; // Energy + Maintenance estimate
        const netAnnualBenefit = recoveredWasteValue - annualOpCosts;

        // 3. Financial Results
        const paybackPeriod = investment / netAnnualBenefit;
        const revenue = annualVolume * pricePerKg;
        let tier = revenue < 15000000 ? "Starter (£299/mo)" : "Professional (£599/mo)";

        // 4. Display Results
        document.getElementById('annualThroughputResult').innerText = annualVolume.toLocaleString();
        document.getElementById('netAnnualBenefitOwnResult').innerText = Math.round(netAnnualBenefit).toLocaleString();
        document.getElementById('paybackPeriodResult').innerText = paybackPeriod.toFixed(1);

        // 5. Tier Recommendation Logic
        document.getElementById('recommendedTier').innerText = tier;

        // 6. Send ROI results to admin email via EmailJS
        sendROIEmail({
            annualVolume: annualVolume.toLocaleString(),
            pricePerKg: pricePerKg.toFixed(2),
            netAnnualBenefit: Math.round(netAnnualBenefit).toLocaleString(),
            paybackPeriod: paybackPeriod.toFixed(1),
            recommendedTier: tier,
            submittedAt: new Date().toUTCString()
        });
    });
});

function sendROIEmail(results) {
    if (typeof emailjs === "undefined") {
        console.warn("EmailJS not loaded. Email not sent.");
        return;
    }

    if (EMAIL_CONFIG.serviceId === "YOUR_EMAILJS_SERVICE_ID") {
        console.warn("EmailJS not configured. Update email-config.js with your credentials.");
        return;
    }

    const params = {
        ...EMAIL_CONFIG.templateParams,
        annual_volume: results.annualVolume,
        price_per_kg: results.pricePerKg,
        net_annual_benefit: results.netAnnualBenefit,
        payback_period: results.paybackPeriod,
        recommended_tier: results.recommendedTier,
        submitted_at: results.submittedAt
    };

    emailjs.send(EMAIL_CONFIG.serviceId, EMAIL_CONFIG.templateId, params)
        .then(() => console.log("ROI results sent to " + EMAIL_CONFIG.adminEmail))
        .catch((err) => console.error("Failed to send ROI email:", err));
}

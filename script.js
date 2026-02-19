document.addEventListener("DOMContentLoaded", () => {
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
        
        // 4. Display Results
        document.getElementById('annualThroughputResult').innerText = annualVolume.toLocaleString();
        document.getElementById('netAnnualBenefitOwnResult').innerText = Math.round(netAnnualBenefit).toLocaleString();
        document.getElementById('paybackPeriodResult').innerText = paybackPeriod.toFixed(1);

        // 5. Tier Recommendation Logic
        const revenue = annualVolume * pricePerKg;
        let tier = revenue < 15000000 ? "Starter (£299/mo)" : "Professional (£599/mo)";
        document.getElementById('recommendedTier').innerText = tier;

        // 6. Show results panel
        document.getElementById('results').style.display = 'block';
    });
});

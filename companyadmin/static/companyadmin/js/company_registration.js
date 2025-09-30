document.addEventListener("DOMContentLoaded", function () {
    console.log("company_registration.js loaded");

    const form = document.getElementById("companyForm");
    if (!form) {
        console.warn("Company form not found!");
        return;
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();

        const payload = {
            CustomerName: form.companyname.value,
            PhoneNumber: form.phonenumber.value,
            CustomerEmail: form.companyemail.value,
            GSTNumber: form.gst.value,
            CustomerContactPerson: form.contactperson.value,
            CustomerContact: form.contactphonenumber.value,
            CustomerAddress: form.comaddress1.value,
            CustomerAddress2: form.comaddress2.value,
            CustomerState: form.state.value,
            CustomerCity: form.city.value,
            CustomerUsername: form.CustomerUsername.value,
            CustomerPassword: form.CustomerPassword.value,
            DeviceModel: "Windows",
            DeviceIdentifier1: form.companyname.value,
            DeviceType: 1,
            Version: "FoodFlash 1.00",
            ProjectName: "FoodFlash 1.00"
        };
        
        console.log("Sending payload:", payload);

        fetch('/food_flash/companyadmin/api/register-company/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
            },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(result => {
            console.log("Success:", result);
            if (result.status === "success") {
                alert("Company registered successfully!");
                window.location.href = '/food_flash/companyadmin/dashboard/';
            } else {
                alert("Error: " + (result.message || "Unknown error occurred"));
            }
        });
    });
});
                                                   

document.getElementById('togglePassword').addEventListener('click', function () {
    const passwordInput = document.getElementById('CustomerPassword');
    const toggleIcon = document.getElementById('toggleIcon');
    
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        toggleIcon.classList.remove('fa-eye-slash');
        toggleIcon.classList.add('fa-eye');
    } else {
        passwordInput.type = 'password';
        toggleIcon.classList.remove('fa-eye');
        toggleIcon.classList.add('fa-eye-slash');
    }
});

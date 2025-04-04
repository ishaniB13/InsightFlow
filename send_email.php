<?php
require './php/PHPMailer-master/src/PHPMailer.php';
require './php/PHPMailer-master/src/SMTP.php';
require './php/PHPMailer-master/src/Exception.php';

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

if ($argc < 5) {
    echo "Insufficient arguments provided.\n";
    exit(1);
}

$recipient_email = $argv[1];
$recipient_name = $argv[2];
$subject = $argv[3];
$temp_file_path = $argv[4];

// Read and decode the JSON file
$json_data = file_get_contents($temp_file_path);
$pdf_base64_list = json_decode($json_data, true);

if (!is_array($pdf_base64_list)) {
    echo "Error: Failed to decode JSON data.\n";
    exit(1);
}

$email_body = "
<p>Thank you for subscribing to our newsletter! We are happy to have you join us on this exciting journey.</p>
<p>Your feedback is invaluable as we strive to make this platform better for everyone. We appreciate your support and look forward to sharing our progress with you!</p>
";

try {
    $mail = new PHPMailer(true);
    $mail->isSMTP();
    $mail->Host = 'smtp.gmail.com';
    $mail->SMTPAuth = true;
    $mail->Username = 'universitatsiegenishanithesis@gmail.com'; // Your Gmail address
    $mail->Password = '<Please enter your app password>'; // Your app password
    $mail->SMTPSecure = PHPMailer::ENCRYPTION_STARTTLS;
    $mail->Port = 587;
    $mail->setFrom('universitatsiegenishanithesis@gmail.com', 'University of Siegen');
    $mail->addAddress($recipient_email, $recipient_name);
    $mail->isHTML(true);
    $mail->Subject = $subject;
    $mail->Body = "<p>Hello $recipient_name,</p>" . $email_body;

    foreach ($pdf_base64_list as $index => $pdf_base64) {
        $decoded_pdf = base64_decode($pdf_base64, true);
        if ($decoded_pdf === false) {
            error_log("Base64 decoding failed for PDF " . ($index + 1));
            echo "Error decoding base64 content for PDF " . ($index + 1) . ". Skipping...\n";
            continue;
        }

        if (substr($decoded_pdf, 0, 2) === "\x1f\x8b") {
            $decompressed_pdf = gzdecode($decoded_pdf);
            if ($decompressed_pdf === false) {
                error_log("Decompression failed for PDF " . ($index + 1));
                echo "Error decompressing the PDF content for PDF " . ($index + 1) . ". Skipping...\n";
                continue;
            }
        } else {
            $decompressed_pdf = $decoded_pdf;
        }

        $mail->addStringAttachment($decompressed_pdf, "Research_PDF_" . ($index + 1) . ".pdf", 'base64', 'application/pdf');
    }

    if ($mail->send()) {
        echo "Email sent successfully to $recipient_name ($recipient_email).\n";
    } else {
        echo "Email could not be sent.\n";
    }
} catch (Exception $e) {
    echo "Email could not be sent. Error: {$mail->ErrorInfo}\n";
}

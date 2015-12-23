CREATE DATABASE CoCoDB;
CREATE USER 'coco'@'localhost' IDENTIFIED BY 'cocorules!';
grant all on CoCoDB.* to 'coco'@'localhost';
